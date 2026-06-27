"""
verdict_engine.py — Main orchestrator for the Verdict Engine (v3).

Wires together the NLI model, stance aggregator, reason builder, and
System 1 classifier fusion into a single ``decide()`` call that consumes
Russell's v2 JSON and emits a FinalOutput.

Routing:
    HIGH_FAKE_MATCH / HIGH_TRUE_MATCH  +  non-empty bucket_a
        → Path 1  (fast path, no NLI, trust the fact-check DB directly)

    bucket_b EMPTY (no qualified props after rerank filter)  [NEW v3]
        → Path Bucket-A-Only  (conflict resolution hierarchy)
          Uses bucket_a similarity tiers + classifier signal to decide.
          No NLI run.

    All other signals with qualified bucket_b props
        → Path 2  (NLI path over filtered bucket_b, then classifier fusion)

Key v3 changes
--------------
  - New _path_bucket_a_only(): fixes the bug where empty bucket_b always
    produced UNVERIFIED even when solid bucket_a evidence existed.
  - Conflict resolution hierarchy (4 rules) lives in aggregator.py.
  - reason_builder.build_conflict_resolution() formats the reason string.

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
# From Russell's Reranker_Calibration_Report.md.
_RERANK_THRESHOLD = 2.0

# Rerank score range for normalisation (clipped then scaled to [0, 1]).
# Based on observed range ~-8 to +10 in the real data.
_RERANK_MIN = -8.0
_RERANK_MAX = 10.0

# Classifier confidence must exceed this to influence the verdict.
_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_rerank(rerank_score: float) -> float:
    """
    Normalise a raw rerank_score from (~-8, +10) to [0, 1].

    Uses linear min-max scaling with clipping.  Only scores above
    _RERANK_THRESHOLD (2.0) are used as weights; this function is
    called after that filter, so inputs are typically in [2, 10].

    Args:
        rerank_score: Raw cross-encoder score.

    Returns:
        Float in [0, 1].
    """
    clipped = max(_RERANK_MIN, min(_RERANK_MAX, rerank_score))
    return (clipped - _RERANK_MIN) / (_RERANK_MAX - _RERANK_MIN)


# ---------------------------------------------------------------------------
# VerdictEngine
# ---------------------------------------------------------------------------

class VerdictEngine:
    """
    Top-level orchestrator for the Verdict Engine (Cyber Teammate).

    Loads all sub-components once at construction time, then processes
    any number of Russell JSON payloads via ``decide()``.

    Args:
        model_name: Reserved for future use (e.g. swapping the NLI backbone).
                    Currently ignored; ``ArabicNLIModel`` always loads
                    ``joeddav/xlm-roberta-large-xnli``.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.nli            = ArabicNLIModel()
        self.aggregator     = StanceAggregator()
        self.reason_builder = ReasonBuilder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, russell_json: dict) -> FinalOutput:
        """
        Consume Russell's v2 RAG output and emit a structured final verdict.

        Args:
            russell_json: A dict conforming to the v2 RussellOutput schema.
                          Extra fields (e.g. _test_note) are silently ignored.

        Returns:
            A ``FinalOutput`` TypedDict with verdict, confidence,
            stance_breakdown, reason, and classifier_fusion.
        """
        verdict_signal: str           = russell_json["verdict_signal"]
        bucket_a: List[BucketAEntry]  = russell_json.get("bucket_a", [])
        bucket_b: List[BucketBEntry]  = russell_json.get("bucket_b", [])
        classifier_signal: Optional[ClassifierSignal] = russell_json.get(
            "classifier_signal"
        )

        # Path 1 — HIGH-confidence fact-check DB hit: skip NLI entirely.
        if verdict_signal in _FAST_PATH_SIGNALS and bucket_a:
            return self._path_one(bucket_a, verdict_signal, classifier_signal)

        # Path Bucket-A-Only (v3) — bucket_b is empty but bucket_a or
        # classifier may still give us a verdict.  Do NOT fall through to
        # Path 2 and return UNVERIFIED by default.
        qualified_props = [
            p for p in bucket_b
            if p.get("rerank_score", -999) > _RERANK_THRESHOLD
        ]
        if not qualified_props:
            return self._path_bucket_a_only(
                bucket_a, verdict_signal, classifier_signal
            )

        return self._path_two(
            russell_json, bucket_a, bucket_b, verdict_signal, classifier_signal
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

        No NLI inference is performed.  Classifier signal is still fused
        as a secondary check even on the fast path.
        """
        best: BucketAEntry = max(bucket_a, key=lambda x: x["similarity"])

        verdict    = _label_to_verdict(best["label"])
        confidence = min(0.95, best["similarity"])

        # Debunk may be empty for saheeh_masr entries — handle gracefully.
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

        # Classifier fusion (secondary check on fast path)
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

        # Build classifier_fusion metadata for transparency
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

        return FinalOutput(
            final_verdict=resolution.verdict,
            confidence=resolution.confidence,
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

        Fusion rules
        ------------
        absent / low-confidence (< 0.80):
            classifier is ignored — not reliable enough to influence.

        REINFORCED — classifier agrees with RAG verdict:
            confidence += 0.05 (capped at 0.95).
            No verdict change.

        OVERRIDDEN — classifier strongly disagrees (confidence ≥ 0.90)
        AND RAG verdict is UNVERIFIED (ambiguous):
            verdict flipped toward classifier's signal.
            Confidence = average of RAG confidence and classifier confidence.
            Note: classifier never overrides a definitive TRUE/FALSE verdict.

        IGNORED — classifier disagrees but RAG is already TRUE/FALSE:
            RAG evidence takes precedence; classifier logged but not applied.

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

        # --- REINFORCED ---
        if clf_verdict == verdict:
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

        # --- OVERRIDDEN — only when RAG is ambiguous (UNVERIFIED) ---
        if verdict == "UNVERIFIED" and clf_confidence >= 0.90:
            new_confidence = round((confidence + clf_confidence) / 2, 4)
            meta = {
                "used": True,
                "label": clf_label,
                "confidence": clf_confidence,
                "effect": "overridden",
            }
            note = (
                f"[Fusion] RAG was UNVERIFIED; System 1 classifier "
                f"({clf_label}, {clf_confidence:.2f}) overrides to {clf_verdict}."
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
