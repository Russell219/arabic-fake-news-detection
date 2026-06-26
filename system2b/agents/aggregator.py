"""
aggregator.py — Math engine for the Verdict Engine's Path 2 output.

Converts a list of weighted NLI stances (from bucket_b) plus the
verdict_signal prior from Russell into a final verdict, a calibrated
confidence score, and a human-readable reasoning summary.

Flow:
    StanceDetail list  +  verdict_signal
           │
           ▼
    score accumulation  (support / refute / neutral totals)
           │
           ▼
    raw_ratio  →  prior adjustment  →  clamped adjusted_ratio
           │
           ▼
    LOW_CONFIDENCE override  (force UNVERIFIED / cap confidence / set flag)
           │
           ▼
    verdict  +  confidence  +  reasoning_summary  +  evidence_sparse
"""

from typing import List, Tuple

from agents.schemas import StanceDetail

# ---------------------------------------------------------------------------
# Signal priors
# ---------------------------------------------------------------------------

SIGNAL_PRIORS: dict[str, float] = {
    # Path 1 signals (won't normally reach Path 2, included for completeness)
    "HIGH_FAKE_MATCH":    -1.0,
    "HIGH_TRUE_MATCH":     1.0,
    # Ambiguous / partial signals
    "HIGH_PARTIAL_MATCH":  0.0,
    "POSSIBLE_FAKE":      -0.3,
    "POSSIBLE_TRUE":       0.3,
    "POSSIBLE_MATCH":      0.0,
    "EVIDENCE_FOUND":      0.1,
    "LOW_CONFIDENCE":      0.0,
}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class StanceAggregator:
    """
    Converts a list of weighted NLI stances into a (verdict, confidence,
    reasoning_summary) triple.

    The aggregator is stateless — all logic lives in ``aggregate()``.
    Instantiate once and call repeatedly.

    Design notes
    ------------
    * Scores passed in via ``StanceDetail.score`` are rerank_score values
      normalised to [0, 1] by the caller (verdict engine).  The aggregator
      treats them as pre-weighted evidence strengths.
    * Only propositions with rerank_score > 2.0 (F1-calibrated threshold)
      are passed in — filtering happens upstream in verdict_engine.py.
    * The prior nudges the ratio by at most ±0.20 (prior × 0.2 weight),
      keeping retrieval signal influential without overriding NLI evidence.
    * Confidence is deliberately capped at 0.95 — the system should never
      claim certainty on open-domain Arabic claims.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def aggregate(
        self,
        stances: List[StanceDetail],
        verdict_signal: str,
    ) -> Tuple[str, float, str, bool]:
        """
        Aggregate NLI stance details into a final verdict.

        Args:
            stances        : List of ``StanceDetail`` dicts produced by the
                             NLI path.  May be empty (yields UNVERIFIED).
            verdict_signal : One of the eight ``RussellOutput`` signal strings.
                             Used to look up the prior in ``SIGNAL_PRIORS``.

        Returns:
            A 4-tuple of:
                verdict           (str)   — "TRUE", "FALSE", or "UNVERIFIED"
                confidence        (float) — calibrated score in (0, 0.95]
                reasoning_summary (str)   — compact debug string
                evidence_sparse   (bool)  — True when LOW_CONFIDENCE signal
                                            triggered sparse-evidence handling
        """
        # ----------------------------------------------------------------
        # 1. Accumulate stance scores
        # ----------------------------------------------------------------
        total_support = 0.0
        total_refute  = 0.0
        total_neutral = 0.0

        for sd in stances:
            if sd["stance"] == "SUPPORTS":
                total_support += sd["score"]
            elif sd["stance"] == "REFUTES":
                total_refute += sd["score"]
            else:
                total_neutral += sd["score"]

        # ----------------------------------------------------------------
        # 2. Raw support ratio
        # ----------------------------------------------------------------
        denominator = total_support + total_refute
        raw_ratio = total_support / denominator if denominator > 0.0 else 0.5

        # ----------------------------------------------------------------
        # 3. Prior adjustment
        # ----------------------------------------------------------------
        prior = SIGNAL_PRIORS.get(verdict_signal, 0.0)
        adjusted_ratio = raw_ratio + (prior * 0.2)

        # Clamp to [0.0, 1.0]
        adjusted_ratio = max(0.0, min(1.0, adjusted_ratio))

        # ----------------------------------------------------------------
        # 4. Verdict mapping
        # ----------------------------------------------------------------
        if adjusted_ratio >= 0.70:
            verdict = "TRUE"
        elif adjusted_ratio <= 0.30:
            verdict = "FALSE"
        else:
            verdict = "UNVERIFIED"

        # ----------------------------------------------------------------
        # 5. Confidence calculation
        # ----------------------------------------------------------------
        # How far the ratio is from the decision boundary (0 → at boundary,
        # 1 → at extreme end).
        distance = abs(adjusted_ratio - 0.5) * 2.0

        # Average evidence quality across all stances (0 if no stances).
        all_scores = [sd["score"] for sd in stances]
        evidence_quality = sum(all_scores) / len(all_scores) if all_scores else 0.0

        # Bonus when every non-neutral stance points in the same direction.
        non_neutral = [sd["stance"] for sd in stances if sd["stance"] != "NEUTRAL"]
        if len(non_neutral) > 0 and len(set(non_neutral)) == 1:
            unanimity_bonus = 0.1
        else:
            unanimity_bonus = 0.0

        confidence = (
            0.5
            + (distance         * 0.3)
            + (evidence_quality * 0.2)
            + unanimity_bonus
        )

        # Cap — we never claim certainty.
        confidence = min(confidence, 0.95)

        # ----------------------------------------------------------------
        # 6. LOW_CONFIDENCE signal overrides
        #
        # When Russell signals LOW_CONFIDENCE, the retrieval layer itself
        # is uncertain.  We apply two overrides regardless of what the NLI
        # math produced:
        #
        #   a) Sparse evidence (< 3 evaluated propositions):
        #      Force verdict to UNVERIFIED — not enough data to decide.
        #
        #   b) Always cap confidence at 0.65 — even strong, unanimous NLI
        #      evidence cannot overcome Russell's retrieval uncertainty.
        # ----------------------------------------------------------------
        evidence_sparse = False

        if verdict_signal == "LOW_CONFIDENCE":
            evidence_sparse = True
            total_evaluated = len(stances)

            # Override (a): too few propositions → force UNVERIFIED
            if total_evaluated < 3:
                verdict = "UNVERIFIED"

            # Override (b): cap confidence regardless of math result
            confidence = min(confidence, 0.65)

        # ----------------------------------------------------------------
        # 7. Reasoning summary
        # ----------------------------------------------------------------
        n_support = sum(1 for sd in stances if sd["stance"] == "SUPPORTS")
        n_refute  = sum(1 for sd in stances if sd["stance"] == "REFUTES")
        n_neutral = sum(1 for sd in stances if sd["stance"] == "NEUTRAL")

        reasoning_summary = (
            f"signal={verdict_signal}, "
            f"support={n_support}, "
            f"refute={n_refute}, "
            f"neutral={n_neutral}, "
            f"raw_ratio={raw_ratio:.3f}, "
            f"adjusted={adjusted_ratio:.3f}, "
            f"evidence_sparse={evidence_sparse}"
        )

        return verdict, round(confidence, 4), reasoning_summary, evidence_sparse
