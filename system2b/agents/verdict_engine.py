"""
verdict_engine.py — Main orchestrator for the Verdict Engine (v4).

Wires together the NLI model, stance aggregator, reason builder, and
System 1 classifier fusion into a single ``decide()`` call that consumes
Russell's v2 JSON and emits a FinalOutput.

Routing (evaluated top to bottom, first match wins):

    LOW_CONFIDENCE  [NEW v4]
        → _path_low_confidence()
          Russell explicitly flags his retrieval as unreliable.
          Handled BEFORE all other paths, including Path 1.
          Sub-cases:
            solid bucket_a (sim >= 0.75):        trust DB, cap confidence 0.70
            no solid bucket_a + clf >= 0.90:     trust classifier, cap 0.70
            no solid bucket_a + clf <  0.90:     UNVERIFIED at 0.50

    HIGH_FAKE_MATCH / HIGH_TRUE_MATCH  +  non-empty bucket_a
        → Path 1  (fast path, no NLI, trust the fact-check DB directly)

    bucket_b EMPTY (no qualified props after rerank filter)
        → Path Bucket-A-Only  (conflict resolution hierarchy)

    All other signals with qualified bucket_b props
        → Path 2  (NLI path over filtered bucket_b, then classifier fusion)

Key v4 changes
--------------
  - LOW_CONFIDENCE is now intercepted first in decide(), before Path 1.
  - _path_low_confidence() handles the three LOW_CONFIDENCE sub-cases.
  - SIGNAL_PRIORS["LOW_CONFIDENCE"] changed from 0.0 to -0.1.
  - aggregate() applies a 0.75 confidence multiplier under LOW_CONFIDENCE.
  - reason_builder.build() accepts low_confidence_detected param.

Key v3 changes (still in effect)
---------------------------------
  - _path_bucket_a_only() with four-rule conflict resolution hierarchy.
  - resolve_bucket_a_conflict() in aggregator.py.
  - build_conflict_resolution() in reason_builder.py.

Key v2 changes (still in effect)
---------------------------------
  - Evidence weighting: rerank_score (cross-encoder) replaces hybrid_score.
  - Evidence filtering: rerank_score > 2.0 only.
  - Classifier fusion via _fuse_classifier().
  - BucketAEntry labels: PARTLY_FALSE, SARCASM, UNVERIFIABLE, UNKNOWN.
  - dialect: open string (DOH, EGY, MSA, etc.).
"""

from typing import List, Optional

from agents.schemas import (
    BucketAEntry,
    BucketBEntry,
    ClassifierSignal,
    FinalOutput,
    StanceDetail,
)
from agents.nli_model import ArabicNLIModel
from agents.aggregator import StanceAggregator, _label_to_verdict
from agents.reason_builder import ReasonBuilder

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Signals that short-circuit directly to the fact-check DB result.
_FAST_PATH_SIGNALS = {"HIGH_FAKE_MATCH", "HIGH_TRUE_MATCH"}

# F1-calibrated threshold: rerank_score > this = real evidence.
_RERANK_THRESHOLD = 2.0

# Rerank score range for normalisation (clipped then scaled to [0, 1]).
_RERANK_MIN = -8.0
_RERANK_MAX = 10.0

# Classifier confidence must exceed this to influence the verdict.
_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.80

# Bucket A similarity threshold for "solid" evidence under LOW_CONFIDENCE.
# Same as aggregator._BUCKET_A_SOLID_THRESHOLD — kept in sync manually.
_LOW_CONF_SOLID_THRESHOLD = 0.75

# Maximum confidence allowed when bucket_a is solid but signal is LOW_CONFIDENCE.
_LOW_CONF_SOLID_CAP = 0.70

# Under LOW_CONFIDENCE with no solid bucket_a, the classifier must reach this
# stricter bar (not the usual 0.80) to be trusted as the fallback signal,
# because Russell's whole retrieval context is flagged unreliable.
_LOW_CONF_CLASSIFIER_THRESHOLD = 0.90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_rerank(rerank_score: float) -> float:
    """Normalise a raw rerank_score from (~-8, +10) to [0, 1]."""
    clipped = max(_RERANK_MIN, min(_RERANK_MAX, rerank_score))
    return (clipped - _RERANK_MIN) / (_RERANK_MAX - _RERANK_MIN)


def _filter_trustworthy_bucket_a(
    bucket_a: List[BucketAEntry],
) -> tuple[List[BucketAEntry], int]:
    """
    Drop bucket_a entries flagged with suspicious_match == True.

    A suspicious match has high lexical similarity but is semantically
    mismatched (e.g. matched on a shared named entity but a different claim).
    The retrieval pipeline flags these so the Verdict Engine does not trust
    them.  Filtered entries are treated as if they were never retrieved.

    Args:
        bucket_a: Raw bucket_a list from Russell's JSON.

    Returns:
        (trustworthy_entries, num_suspicious_dropped)
    """
    trustworthy = [
        e for e in bucket_a
        if not e.get("suspicious_match", False)
    ]
    dropped = len(bucket_a) - len(trustworthy)
    return trustworthy, dropped


# ---------------------------------------------------------------------------
# VerdictEngine
# ---------------------------------------------------------------------------

class VerdictEngine:
    """
    Top-level orchestrator for the Verdict Engine (Cyber Teammate).

    Loads all sub-components once at construction time, then processes
    any number of Russell JSON payloads via ``decide()``.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.nli            = ArabicNLIModel()
        self.aggregator     = StanceAggregator()
        self.reason_builder = ReasonBuilder()
        self._last_suspicious_dropped = 0  # set per decide() call

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, russell_json: dict) -> FinalOutput:
        """
        Consume Russell's v2 RAG output and emit a structured final verdict.

        Routing order (first match wins):
            1. LOW_CONFIDENCE signal → _path_low_confidence()
            2. HIGH_FAKE/TRUE_MATCH + bucket_a → _path_one()
            3. No qualified bucket_b props → _path_bucket_a_only()
            4. Qualified bucket_b props → _path_two()
        """
        verdict_signal: str           = russell_json["verdict_signal"]
        bucket_a_raw: List[BucketAEntry] = russell_json.get("bucket_a", [])
        bucket_b: List[BucketBEntry]  = russell_json.get("bucket_b", [])
        classifier_signal: Optional[ClassifierSignal] = russell_json.get(
            "classifier_signal"
        )

        # ── BUG 1 FIX: drop suspicious bucket_a matches ──────────────────
        # suspicious_match == True means the retrieval flagged the match as
        # spurious (high lexical overlap, wrong claim).  We treat these as if
        # bucket_a were empty for those entries — fall back to NLI / classifier.
        bucket_a, n_suspicious = _filter_trustworthy_bucket_a(bucket_a_raw)
        self._last_suspicious_dropped = n_suspicious  # for reason transparency

        # ── INTERCEPT 1: LOW_CONFIDENCE ──────────────────────────────────
        # Must come BEFORE Path 1.  Even a HIGH_FAKE_MATCH with LOW_CONFIDENCE
        # means Russell is unsure of his own retrieval — we must not blindly
        # trust it at full confidence.
        if verdict_signal == "LOW_CONFIDENCE":
            result = self._path_low_confidence(bucket_a, classifier_signal)
            return self._inject_suspicious_note(result, n_suspicious)

        # ── INTERCEPT 2: Path 1 fast path ────────────────────────────────
        # Only valid if a trustworthy bucket_a entry survived the filter.
        if verdict_signal in _FAST_PATH_SIGNALS and bucket_a:
            result = self._path_one(bucket_a, verdict_signal, classifier_signal)
            return self._inject_suspicious_note(result, n_suspicious)

        # ── INTERCEPT 3: no qualified bucket_b props ──────────────────────
        qualified_props = [
            p for p in bucket_b
            if p.get("rerank_score", -999) > _RERANK_THRESHOLD
        ]
        if not qualified_props:
            result = self._path_bucket_a_only(
                bucket_a, verdict_signal, classifier_signal
            )
            return self._inject_suspicious_note(result, n_suspicious)

        # ── INTERCEPT 4: full NLI path ────────────────────────────────────
        result = self._path_two(
            russell_json, bucket_a, bucket_b, verdict_signal, classifier_signal
        )
        return self._inject_suspicious_note(result, n_suspicious)

    def _inject_suspicious_note(
        self, result: FinalOutput, n_suspicious: int
    ) -> FinalOutput:
        """Prepend a suspicious-match note to result['reason'] if any were dropped."""
        note = self.reason_builder.suspicious_match_note(n_suspicious)
        if note:
            result["reason"] = f"{note} {result['reason']}"
        return result

    # ------------------------------------------------------------------
    # Path LOW_CONFIDENCE (v4) — Russell flags his retrieval as unreliable
    # ------------------------------------------------------------------

    def _path_low_confidence(
        self,
        bucket_a: List[BucketAEntry],
        classifier_signal: Optional[ClassifierSignal],
    ) -> FinalOutput:
        """
        Handle LOW_CONFIDENCE signal before any other routing.

        Russell's LOW_CONFIDENCE means his retrieval pipeline is unreliable —
        matches in bucket_a may be false positives, bucket_b has nothing
        qualifying, and the classifier alone is never enough.

        Sub-cases:

        Sub-case A — solid bucket_a (sim >= 0.75):
            A very high similarity in a fact-check DB is hard to fake even
            under low-confidence retrieval.  We trust it, but cap confidence
            at 0.70 (not 0.90) and add a warning.

        Sub-case B — no solid bucket_a + CONFIDENT classifier (>= 0.90):
            No reliable fact-check evidence, but a very confident classifier
            (>= 0.90) is trusted as the fallback signal, with confidence capped
            at 0.70 because Russell's retrieval context is unreliable.

        Sub-case C — no solid bucket_a + WEAK classifier (< 0.90):
            Nothing reliable to act on. Output UNVERIFIED at confidence 0.50.
        """
        # Defensive: ensure no suspicious matches slipped through.
        bucket_a = [e for e in bucket_a if not e.get("suspicious_match", False)]

        best_a = max(bucket_a, key=lambda x: x["similarity"]) if bucket_a else None
        sim    = best_a["similarity"] if best_a else 0.0

        absent_fusion: dict = {
            "used": False, "label": None, "confidence": None, "effect": "absent"
        }

        # Sub-case A: solid bucket_a — trust but cap
        if best_a and sim >= _LOW_CONF_SOLID_THRESHOLD:
            verdict    = _label_to_verdict(best_a["label"])
            confidence = round(min(_LOW_CONF_SOLID_CAP, sim), 4)
            source     = best_a.get("source", "fact-check DB")

            reason = (
                f"[LOW_CONFIDENCE + Solid Bucket A] "
                f"Russell reported low retrieval confidence, but a high-similarity "
                f"fact-check match was found (similarity {sim:.3f}, source: {source}). "
                f"The fact-checked verdict ({verdict}) is retained, but confidence "
                f"is capped at {_LOW_CONF_SOLID_CAP} due to low retrieval reliability. "
                f"⚠️ Russell reported low retrieval confidence, but solid "
                f"fact-checked evidence was found."
            )

            return FinalOutput(
                final_verdict=verdict,
                confidence=confidence,
                stance_breakdown=[],
                reason=reason,
                classifier_fusion=absent_fusion,
            )

        # Sub-cases B / C: no solid bucket_a
        clf_label = classifier_signal.get("label") if classifier_signal else None
        clf_conf  = float(classifier_signal.get("confidence", 0.0)) if classifier_signal else 0.0

        # Sub-case B — CONFIDENT classifier (>= 0.90): trust it, cap at 0.70.
        # Under LOW_CONFIDENCE we demand the stricter 0.90 bar (not 0.80),
        # because Russell's whole retrieval context is flagged unreliable.
        if clf_label and clf_conf >= _LOW_CONF_CLASSIFIER_THRESHOLD:
            clf_verdict = "FALSE" if clf_label == "fake" else "TRUE"
            confidence  = round(min(_LOW_CONF_SOLID_CAP, clf_conf), 4)

            reason = (
                f"[LOW_CONFIDENCE + Confident Classifier] "
                f"Russell reported low retrieval confidence and no solid "
                f"fact-checked evidence exists, but System 1 classifier is "
                f"highly confident ({clf_label}, {clf_conf:.3f}). "
                f"The classifier verdict ({clf_verdict}) is used as the fallback "
                f"signal, with confidence capped at {_LOW_CONF_SOLID_CAP} due to "
                f"low retrieval reliability. "
                f"⚠️ Low retrieval confidence reported by RAG engine."
            )

            clf_fusion: dict = {
                "used": True,
                "label": clf_label,
                "confidence": clf_conf,
                "effect": "resolved_low_confidence",
            }

            return FinalOutput(
                final_verdict=clf_verdict,
                confidence=confidence,
                stance_breakdown=[],
                reason=reason,
                classifier_fusion=clf_fusion,
            )

        # Sub-case C — WEAK or absent classifier: UNVERIFIED.
        reason = (
            "[LOW_CONFIDENCE + No Solid Evidence] "
            "Russell reported low confidence in retrieval and no solid "
            "fact-checked evidence exists. "
            "System 1 classifier is weak or absent and is not trusted alone. "
            "Verdict is uncertain. "
            "⚠️ Low retrieval confidence reported by RAG engine."
        )

        clf_fusion = {
            "used": False,
            "label": clf_label,
            "confidence": clf_conf if clf_label else None,
            "effect": "ignored_low_confidence",
        }

        return FinalOutput(
            final_verdict="UNVERIFIED",
            confidence=0.50,
            stance_breakdown=[],
            reason=reason,
            classifier_fusion=clf_fusion,
        )

    # ------------------------------------------------------------------
    # Path 1 — Fast path (known fact-check DB hit)
    # ------------------------------------------------------------------

    def _path_one(
        self,
        bucket_a: List[BucketAEntry],
        verdict_signal: str,
        classifier_signal: Optional[ClassifierSignal],
    ) -> FinalOutput:
        """
        Derive the verdict directly from the highest-similarity Bucket A entry.
        Only reached when verdict_signal is HIGH_FAKE_MATCH or HIGH_TRUE_MATCH.
        No NLI inference is performed.
        """
        best: BucketAEntry = max(bucket_a, key=lambda x: x["similarity"])

        verdict    = _label_to_verdict(best["label"])
        confidence = min(0.95, best["similarity"])

        debunk_text = best.get("debunk", "") or "N/A"
        claim_type  = "fake" if verdict == "FALSE" else (
            "true" if verdict == "TRUE" else "partially verified"
        )

        base_reason = (
            f"Russell found a high-similarity match "
            f"({best['similarity']:.3f}) to a known {claim_type} claim. "
            f"Source: {best['source']}. "
            f"Debunk: {debunk_text}"
        )

        verdict, confidence, fusion_meta, fusion_note = self._fuse_classifier(
            verdict, confidence, classifier_signal
        )
        reason = base_reason + (f" {fusion_note}" if fusion_note else "")

        return FinalOutput(
            final_verdict=verdict,
            confidence=round(confidence, 4),
            stance_breakdown=[],
            reason=reason,
            classifier_fusion=fusion_meta,
        )

    # ------------------------------------------------------------------
    # Path Bucket-A-Only (v3) — no qualified bucket_b propositions
    # ------------------------------------------------------------------

    def _path_bucket_a_only(
        self,
        bucket_a: List[BucketAEntry],
        verdict_signal: str,
        classifier_signal: Optional[ClassifierSignal],
    ) -> FinalOutput:
        """
        Resolve verdict when bucket_b has no qualifying propositions.

        Delegates to StanceAggregator.resolve_bucket_a_conflict() which
        implements the four-rule hierarchy:

            Rule 1  — solid bucket_a (sim >= 0.75): trust fact-check DB
            Rule 2a — moderate bucket_a + confident disagreeing classifier:
                       CONFLICT → UNVERIFIED
            Rule 2b — moderate bucket_a + weak/agreeing classifier:
                       trust fact-check DB at discounted confidence
            Rule 3a — no bucket_a + confident classifier: use classifier
            Rule 3b — nothing reliable: UNVERIFIED at 0.50

        Args:
            bucket_a          : Bucket A entries (may be empty).
            verdict_signal    : Russell's retrieval signal.
            classifier_signal : System 1's raw output (may be None).

        Returns:
            A ``FinalOutput`` dict.
        """
        clf_dict = dict(classifier_signal) if classifier_signal else None
        resolution = self.aggregator.resolve_bucket_a_conflict(
            bucket_a=bucket_a,
            classifier_signal=clf_dict,
            verdict_signal=verdict_signal,
        )

        # Build the formatted reason string
        clf_label = classifier_signal.get("label") if classifier_signal else None
        clf_conf  = float(classifier_signal.get("confidence", 0.0)) if classifier_signal else 0.0
        best_a    = max(bucket_a, key=lambda x: x["similarity"]) if bucket_a else None

        reason = self.reason_builder.build_conflict_resolution(
            rule=resolution.rule,
            verdict=resolution.verdict,
            bucket_a_similarity=best_a["similarity"] if best_a else 0.0,
            bucket_a_source=best_a.get("source", "") if best_a else "",
            clf_label=clf_label,
            clf_confidence=clf_conf,
            base_reason=resolution.reason,
        )

        verdict     = resolution.verdict
        confidence  = resolution.confidence

        # ── BUG 2 FIX: let a confident classifier RESOLVE an UNVERIFIED ──
        # Conflict resolution can return UNVERIFIED (Rule 2a conflict, Rule 3b
        # no-evidence). Previously the classifier never got a second chance
        # here, so System 3 dumped these to UNVERIFIED. Now we run fusion.
        # Exception: LOW_CONFIDENCE results are NOT resolved — Russell's signal
        # explicitly says his retrieval (and the surfaced classifier context)
        # is unreliable, so we respect the UNVERIFIED.
        fusion_meta = {
            "used": resolution.rule in ("no_evidence_clf_strong",),
            "label": clf_label,
            "confidence": clf_conf if clf_label else None,
            "effect": {
                "solid_bucket_a":         "ignored",
                "moderate_conflict":      "conflict",
                "moderate_agree":         "ignored",
                "no_evidence_clf_strong": "primary",
                "no_evidence_clf_weak":   "ignored",
            }.get(resolution.rule, "absent"),
        }

        if verdict == "UNVERIFIED" and verdict_signal != "LOW_CONFIDENCE":
            verdict, confidence, fusion_meta, fusion_note = self._fuse_classifier(
                verdict, confidence, classifier_signal
            )
            if fusion_note:
                reason += f" {fusion_note}"

        return FinalOutput(
            final_verdict=verdict,
            confidence=confidence,
            stance_breakdown=[],
            reason=reason,
            classifier_fusion=fusion_meta,
        )

    # ------------------------------------------------------------------
    # Path 2 — NLI path (run inference over filtered bucket_b)
    # ------------------------------------------------------------------

    def _path_two(
        self,
        russell_json: dict,
        bucket_a: List[BucketAEntry],
        bucket_b: List[BucketBEntry],
        verdict_signal: str,
        classifier_signal: Optional[ClassifierSignal],
    ) -> FinalOutput:
        """
        Filter bucket_b by rerank threshold, run Arabic NLI, aggregate,
        then fuse System 1's classifier signal.
        """
        claim: str = russell_json["claim"]

        # Rerank filter — already computed in decide() but re-derive here
        # so _path_two stays self-contained and callable independently.
        qualified_props = [
            p for p in bucket_b
            if p.get("rerank_score", -999) > _RERANK_THRESHOLD
        ]

        # Sanity guard — should not happen since decide() routes empty
        # qualified_props to _path_bucket_a_only, but handle defensively.
        if not qualified_props:
            return self._path_bucket_a_only(
                bucket_a, verdict_signal, classifier_signal
            )

        # ----------------------------------------------------------------
        # Run NLI over qualified propositions.
        # Use proposition_display if available (decontextualized), else
        # fall back to proposition.
        # ----------------------------------------------------------------
        stance_breakdown: List[StanceDetail] = []

        for prop in qualified_props:
            text_for_nli = prop.get("proposition_display") or prop["proposition"]
            stance       = self.nli.predict(claim, text_for_nli)
            norm_score   = _normalise_rerank(prop["rerank_score"])

            stance_breakdown.append(
                StanceDetail(
                    evidence=f"{prop['title']} ({prop['source']})",
                    stance=stance,
                    score=norm_score,
                    rerank_score=prop["rerank_score"],
                )
            )

        # ----------------------------------------------------------------
        # Aggregate stances
        # ----------------------------------------------------------------
        verdict, confidence, reasoning_summary, evidence_sparse = \
            self.aggregator.aggregate(
                stances=stance_breakdown,
                verdict_signal=verdict_signal,
            )

        # ----------------------------------------------------------------
        # Build reason string
        # ----------------------------------------------------------------
        best_a = max(bucket_a, key=lambda x: x["similarity"]) if bucket_a else None

        reason = self.reason_builder.build(
            verdict=verdict,
            verdict_signal=verdict_signal,
            bucket_a_present=best_a is not None,
            bucket_a_similarity=best_a["similarity"] if best_a else 0.0,
            bucket_a_source=best_a["source"] if best_a else "",
            bucket_a_debunk=best_a.get("debunk", "") or "N/A" if best_a else "",
            stance_breakdown=stance_breakdown,
            evidence_sparse=evidence_sparse,
            low_confidence_detected=(verdict_signal == "LOW_CONFIDENCE"),
        )

        # ----------------------------------------------------------------
        # Classifier fusion
        # ----------------------------------------------------------------
        verdict, confidence, fusion_meta, fusion_note = self._fuse_classifier(
            verdict, confidence, classifier_signal
        )
        if fusion_note:
            reason += f" {fusion_note}"

        return FinalOutput(
            final_verdict=verdict,
            confidence=confidence,
            stance_breakdown=stance_breakdown,
            reason=reason,
            classifier_fusion=fusion_meta,
        )

    # ------------------------------------------------------------------
    # Classifier fusion
    # ------------------------------------------------------------------

    def _fuse_classifier(
        self,
        verdict: str,
        confidence: float,
        classifier_signal: Optional[ClassifierSignal],
    ) -> tuple[str, float, dict, str]:
        """
        Fuse System 1's (Sarah's) classifier output with the RAG verdict.

        Fusion rules (v5 — Bug 2 fix)
        -----------------------------
        absent / low-confidence (< 0.80):
            classifier is ignored — not reliable enough to influence.

        REINFORCED — classifier agrees with a definitive RAG verdict:
            confidence += 0.05 (capped at 0.95).  No verdict change.

        RESOLVED — RAG verdict is UNVERIFIED and classifier is confident
        (>= 0.80):
            The classifier RESOLVES the uncertainty.  This is the key Bug 2
            fix: previously System 3 left UNVERIFIED in place unless the
            classifier hit 0.90, so a correct 0.80–0.90 classifier was wasted.
            Verdict becomes the classifier verdict.
            Confidence scales with classifier confidence but is capped:
              - clf >= 0.90 → cap 0.85  (strong resolution)
              - clf >= 0.80 → cap 0.75  (moderate resolution)

        IGNORED — classifier disagrees but RAG is already definitive (TRUE/FALSE):
            RAG evidence (fact-check / NLI) takes precedence; classifier logged
            but not applied.

        Args:
            verdict           : Current RAG-derived verdict.
            confidence        : Current RAG-derived confidence.
            classifier_signal : System 1's raw output (may be None).

        Returns:
            (updated_verdict, updated_confidence, fusion_meta_dict, note_str)
        """
        absent_meta = {
            "used": False,
            "label": None,
            "confidence": None,
            "effect": "absent",
        }

        if not classifier_signal:
            return verdict, confidence, absent_meta, ""

        clf_label      = classifier_signal.get("label", "")        # "real" / "fake"
        clf_confidence = float(classifier_signal.get("confidence", 0.0))

        if clf_confidence < _CLASSIFIER_CONFIDENCE_THRESHOLD:
            meta = {
                "used": False,
                "label": clf_label,
                "confidence": clf_confidence,
                "effect": "ignored",
            }
            return verdict, confidence, meta, ""

        # Map classifier label to verdict vocabulary
        clf_verdict = "FALSE" if clf_label == "fake" else "TRUE"

        # --- REINFORCED — classifier agrees with a definitive RAG verdict ---
        if verdict in ("TRUE", "FALSE") and clf_verdict == verdict:
            new_confidence = min(0.95, confidence + 0.05)
            meta = {
                "used": True,
                "label": clf_label,
                "confidence": clf_confidence,
                "effect": "reinforced",
            }
            note = (
                f"[Fusion] System 1 classifier agrees ({clf_label}, "
                f"{clf_confidence:.2f}); confidence boosted."
            )
            return verdict, round(new_confidence, 4), meta, note

        # --- RESOLVED — RAG was UNVERIFIED, confident classifier decides it ---
        # This is the Bug 2 fix.  A confident classifier (>= 0.80) now RESOLVES
        # an UNVERIFIED RAG verdict instead of being discarded.
        if verdict == "UNVERIFIED":
            # Confidence cap scales with how confident the classifier is.
            cap = 0.85 if clf_confidence >= 0.90 else 0.75
            new_confidence = round(min(cap, max(confidence, clf_confidence * 0.85)), 4)
            meta = {
                "used": True,
                "label": clf_label,
                "confidence": clf_confidence,
                "effect": "resolved",
            }
            note = (
                f"[Fusion] RAG was UNVERIFIED; System 1 classifier "
                f"({clf_label}, {clf_confidence:.2f}) resolves verdict to "
                f"{clf_verdict} (confidence capped at {cap})."
            )
            return clf_verdict, new_confidence, meta, note

        # --- IGNORED — classifier disagrees but RAG has a definitive verdict ---
        meta = {
            "used": False,
            "label": clf_label,
            "confidence": clf_confidence,
            "effect": "ignored",
        }
        note = (
            f"[Fusion] System 1 classifier ({clf_label}, {clf_confidence:.2f}) "
            f"disagrees with RAG verdict ({verdict}); RAG evidence takes precedence."
        )
        return verdict, confidence, meta, note
