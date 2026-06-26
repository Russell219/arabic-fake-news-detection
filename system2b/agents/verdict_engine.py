"""
verdict_engine.py — Main orchestrator for the Verdict Engine (v2).

Wires together the NLI model, stance aggregator, reason builder, and
System 1 classifier fusion into a single ``decide()`` call that consumes
Russell's v2 JSON and emits a FinalOutput.

Routing:
    HIGH_FAKE_MATCH / HIGH_TRUE_MATCH  +  non-empty bucket_a
        → Path 1  (fast path, no NLI, trust the fact-check DB directly)

    All other signals  OR  empty bucket_a
        → Path 2  (NLI path over filtered bucket_b, then classifier fusion)

Key v2 changes
--------------
  - Evidence weighting: hybrid_score (tiny RRF float) → rerank_score
    (cross-encoder, range ~-8 to +10), normalised to [0, 1].
  - Evidence filtering: only propositions with rerank_score > 2.0 are
    passed to NLI (F1-calibrated threshold from Reranker_Calibration_Report).
  - Classifier fusion: System 1's classifier_signal is fused with the
    NLI/RAG verdict.  Fusion rules are documented in _fuse_classifier().
  - BucketAEntry labels updated: PARTLY_FALSE, SARCASM, UNVERIFIABLE, UNKNOWN.
  - dialect field is now an open string (DOH, EGY, MSA, etc.).
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
from agents.aggregator import StanceAggregator
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


def _label_to_verdict(label: str) -> str:
    """
    Map a BucketAEntry label to a FinalOutput verdict string.

    New v2 labels handled:
        TRUE         → TRUE
        FALSE        → FALSE
        PARTLY_FALSE → UNVERIFIED  (partial; too nuanced to call FALSE)
        SARCASM      → UNVERIFIED  (intent unclear without context)
        UNVERIFIABLE → UNVERIFIED
        UNKNOWN      → UNVERIFIED
    """
    if label == "TRUE":
        return "TRUE"
    if label == "FALSE":
        return "FALSE"
    return "UNVERIFIED"


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

        if verdict_signal in _FAST_PATH_SIGNALS and bucket_a:
            return self._path_one(bucket_a, verdict_signal, classifier_signal)

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

        # ----------------------------------------------------------------
        # Filter: only keep propositions that pass the rerank threshold.
        # rerank_score > 2.0 = F1-calibrated "real evidence" boundary.
        # ----------------------------------------------------------------
        qualified_props = [
            p for p in bucket_b
            if p.get("rerank_score", -999) > _RERANK_THRESHOLD
        ]

        # ----------------------------------------------------------------
        # Handle empty / no-qualified-evidence cases
        # ----------------------------------------------------------------
        if not qualified_props:
            if verdict_signal == "LOW_CONFIDENCE":
                verdict    = "UNVERIFIED"
                confidence = 0.5
                reason = (
                    "Russell returned low confidence; evidence is sparse. "
                    "No propositions passed the rerank quality threshold (> 2.0). "
                    "Evidence is insufficient; verdict is uncertain. "
                    "⚠️ Warning: Russell retrieved sparse evidence. "
                    "Treat this verdict with caution."
                )
            else:
                verdict    = "UNVERIFIED"
                confidence = 0.1
                reason = self.reason_builder.build(
                    verdict="UNVERIFIED",
                    verdict_signal=verdict_signal,
                    bucket_a_present=bool(bucket_a),
                    bucket_a_similarity=bucket_a[0]["similarity"] if bucket_a else 0.0,
                    bucket_a_source=bucket_a[0]["source"] if bucket_a else "",
                    bucket_a_debunk=bucket_a[0].get("debunk", "") or "N/A" if bucket_a else "",
                    stance_breakdown=[],
                    evidence_sparse=False,
                )

            verdict, confidence, fusion_meta, fusion_note = self._fuse_classifier(
                verdict, confidence, classifier_signal
            )
            if fusion_note:
                reason += f" {fusion_note}"

            return FinalOutput(
                final_verdict=verdict,
                confidence=round(confidence, 4),
                stance_breakdown=[],
                reason=reason,
                classifier_fusion=fusion_meta,
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
