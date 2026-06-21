"""
verdict_engine.py — Main orchestrator for the Verdict Engine.

Wires together the NLI model, stance aggregator, and reason builder into a
single ``decide()`` call that consumes Russell's JSON and emits a FinalOutput.

Routing:
    HIGH_FAKE_MATCH / HIGH_TRUE_MATCH  +  non-empty bucket_a
        → Path 1  (fast path, no NLI, trust the fact-check DB directly)

    All other signals  OR  empty bucket_a
        → Path 2  (NLI path, run xlm-roberta over every bucket_b proposition)
"""

from typing import List

from agents.schemas import (
    BucketAEntry,
    BucketBEntry,
    FinalOutput,
    RussellOutput,
    StanceDetail,
)
from agents.nli_model import ArabicNLIModel
from agents.aggregator import StanceAggregator
from agents.reason_builder import ReasonBuilder

# Signals that short-circuit directly to the fact-check DB result.
_FAST_PATH_SIGNALS = {"HIGH_FAKE_MATCH", "HIGH_TRUE_MATCH"}


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
        Consume Russell's RAG output and emit a structured final verdict.

        Args:
            russell_json: A dict conforming to ``RussellOutput``.  Passed as
                          a plain dict so callers can deserialise JSON directly
                          without an explicit cast.

        Returns:
            A ``FinalOutput`` TypedDict with verdict, confidence,
            stance_breakdown, and reason.
        """
        verdict_signal: str             = russell_json["verdict_signal"]
        bucket_a: List[BucketAEntry]    = russell_json.get("bucket_a", [])
        bucket_b: List[BucketBEntry]    = russell_json.get("bucket_b", [])

        if verdict_signal in _FAST_PATH_SIGNALS and bucket_a:
            return self._path_one(bucket_a, verdict_signal)

        return self._path_two(russell_json, bucket_a, bucket_b, verdict_signal)

    # ------------------------------------------------------------------
    # Path 1 — Fast path (known fact-check DB hit)
    # ------------------------------------------------------------------

    def _path_one(
        self,
        bucket_a: List[BucketAEntry],
        verdict_signal: str,
    ) -> FinalOutput:
        """
        Derive the verdict directly from the highest-similarity Bucket A entry.

        No NLI inference is performed.  Confidence is capped at 0.95 to match
        the engine-wide convention of never claiming certainty.

        Args:
            bucket_a       : Non-empty list of fact-check DB matches.
            verdict_signal : The triggering signal (HIGH_FAKE_MATCH or
                             HIGH_TRUE_MATCH), passed through to the reason.

        Returns:
            A ``FinalOutput`` dict.
        """
        best: BucketAEntry = max(bucket_a, key=lambda x: x["similarity"])

        # Map the fact-check label to our verdict vocabulary.
        # PARTIALLY_TRUE → UNVERIFIED (nuanced; neither fully true nor false).
        label = best["label"]
        if label == "TRUE":
            verdict = "TRUE"
        elif label == "FALSE":
            verdict = "FALSE"
        else:
            verdict = "UNVERIFIED"

        confidence: float = min(0.95, best["similarity"])

        claim_type = "fake" if verdict == "FALSE" else "true"
        reason = (
            f"Russell found a high-similarity match "
            f"({best['similarity']:.3f}) to a known {claim_type} claim. "
            f"Source: {best['source']}. "
            f"Debunk: {best.get('debunk', 'N/A')}"
        )

        return FinalOutput(
            final_verdict=verdict,
            confidence=round(confidence, 4),
            stance_breakdown=[],
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Path 2 — NLI path (run inference over bucket_b propositions)
    # ------------------------------------------------------------------

    def _path_two(
        self,
        russell_json: dict,
        bucket_a: List[BucketAEntry],
        bucket_b: List[BucketBEntry],
        verdict_signal: str,
    ) -> FinalOutput:
        """
        Run Arabic NLI over every Bucket B proposition and aggregate results.

        When bucket_b is empty the engine returns UNVERIFIED with low
        confidence, since there is no evidence to reason over.

        Args:
            russell_json   : Full Russell payload (for claim text and metadata).
            bucket_a       : Bucket A entries — used only to populate the
                             reason string, not for verdict logic here.
            bucket_b       : List of trusted-source propositions to evaluate.
            verdict_signal : Russell's signal, passed to aggregator as a prior.

        Returns:
            A ``FinalOutput`` dict.
        """
        claim: str = russell_json["claim"]

        # ----------------------------------------------------------------
        # Handle empty bucket_b gracefully — nothing to run NLI over.
        # ----------------------------------------------------------------
        if not bucket_b:
            reason = self.reason_builder.build(
                verdict="UNVERIFIED",
                verdict_signal=verdict_signal,
                bucket_a_present=bool(bucket_a),
                bucket_a_similarity=bucket_a[0]["similarity"] if bucket_a else 0.0,
                bucket_a_source=bucket_a[0]["source"] if bucket_a else "",
                bucket_a_debunk=bucket_a[0].get("debunk", "N/A") if bucket_a else "",
                stance_breakdown=[],
            )
            return FinalOutput(
                final_verdict="UNVERIFIED",
                confidence=0.1,
                stance_breakdown=[],
                reason=reason,
            )

        # ----------------------------------------------------------------
        # Run NLI — one forward pass per proposition.
        # ----------------------------------------------------------------
        stance_breakdown: List[StanceDetail] = []

        for prop in bucket_b:
            stance = self.nli.predict(claim, prop["proposition"])
            stance_breakdown.append(
                StanceDetail(
                    evidence=f"{prop['title']} ({prop['source']})",
                    stance=stance,
                    score=prop["hybrid_score"],
                )
            )

        # ----------------------------------------------------------------
        # Aggregate stances into (verdict, confidence, reasoning_summary).
        # ----------------------------------------------------------------
        verdict, confidence, reasoning_summary = self.aggregator.aggregate(
            stances=stance_breakdown,
            verdict_signal=verdict_signal,
        )

        # ----------------------------------------------------------------
        # Build the human-readable reason string.
        # ----------------------------------------------------------------
        # Prefer the best Bucket A entry if one exists (for context in reason).
        best_a: BucketAEntry | None = (
            max(bucket_a, key=lambda x: x["similarity"]) if bucket_a else None
        )

        reason = self.reason_builder.build(
            verdict=verdict,
            verdict_signal=verdict_signal,
            bucket_a_present=best_a is not None,
            bucket_a_similarity=best_a["similarity"] if best_a else 0.0,
            bucket_a_source=best_a["source"] if best_a else "",
            bucket_a_debunk=best_a.get("debunk", "N/A") if best_a else "",
            stance_breakdown=stance_breakdown,
        )

        return FinalOutput(
            final_verdict=verdict,
            confidence=confidence,
            stance_breakdown=stance_breakdown,
            reason=reason,
        )
