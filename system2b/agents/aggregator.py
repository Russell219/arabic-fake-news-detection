"""
aggregator.py — Math engine for the Verdict Engine's Path 2 output.

Converts a list of weighted NLI stances (from bucket_b) plus the
verdict_signal prior from Russell into a final verdict, a calibrated
confidence score, and a human-readable reasoning summary.

Flow (NLI path — bucket_b present):
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

Conflict resolution path (bucket_b empty — added v3):
    bucket_a entries  +  classifier_signal
           │
           ▼
    resolve_bucket_a_conflict()
           │
           ▼
    ConflictResolution(verdict, confidence, rule, reason)
"""

from typing import List, NamedTuple, Optional, Tuple

from agents.schemas import BucketAEntry, StanceDetail

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
    "LOW_CONFIDENCE":      -0.1,   # weak tilt toward uncertainty
}

# ---------------------------------------------------------------------------
# Bucket A similarity thresholds
# ---------------------------------------------------------------------------

# >= SOLID_THRESHOLD  → fact-check evidence is trustworthy; overrides classifier
_BUCKET_A_SOLID_THRESHOLD    = 0.75
# >= MODERATE_LOW AND < SOLID → moderate; classifier can challenge if very confident
_BUCKET_A_MODERATE_THRESHOLD = 0.60

# Classifier must be at least this confident to challenge moderate bucket_a
_CLASSIFIER_CHALLENGE_THRESHOLD = 0.90


# ---------------------------------------------------------------------------
# Label helper (also used by verdict_engine.py — defined here to avoid circular import)
# ---------------------------------------------------------------------------

def _label_to_verdict(label: str) -> str:
    """
    Map a BucketAEntry label to a FinalOutput verdict string.

        TRUE         → TRUE
        FALSE        → FALSE
        PARTLY_FALSE → UNVERIFIED
        SARCASM      → UNVERIFIED
        UNVERIFIABLE → UNVERIFIED
        UNKNOWN      → UNVERIFIED
    """
    if label == "TRUE":
        return "TRUE"
    if label == "FALSE":
        return "FALSE"
    return "UNVERIFIED"


# ---------------------------------------------------------------------------
# Result type for conflict resolution
# ---------------------------------------------------------------------------

class ConflictResolution(NamedTuple):
    """
    Output of ``StanceAggregator.resolve_bucket_a_conflict()``.

    Attributes:
        verdict    : "TRUE", "FALSE", or "UNVERIFIED"
        confidence : Calibrated confidence score in (0, 0.95]
        rule       : Which rule fired — "solid_bucket_a", "moderate_conflict",
                     "moderate_agree", "no_evidence_clf_strong",
                     "no_evidence_clf_weak"
        reason     : Human-readable explanation string (passed to FinalOutput)
    """
    verdict:    str
    confidence: float
    rule:       str
    reason:     str


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
    # Conflict resolution (v3) — bucket_b is empty
    # ------------------------------------------------------------------

    def resolve_bucket_a_conflict(
        self,
        bucket_a: List[BucketAEntry],
        classifier_signal: Optional[dict],
        verdict_signal: str = "",
    ) -> ConflictResolution:
        """
        Resolve the verdict when bucket_b is empty (no NLI evidence).

        Implements the four-rule hierarchy, with a LOW_CONFIDENCE pre-check:

        LOW_CONFIDENCE pre-check (NEW):
            When Russell's own signal is LOW_CONFIDENCE, his retrieval is
            unreliable regardless of what bucket_a shows.  Even solid bucket_a
            matches are demoted — we cannot trust that the match is genuine if
            Russell himself flagged low confidence.  Return UNVERIFIED at 0.50
            with a warning, bypassing all rules.

        Rule 1 — SOLID BUCKET A (similarity >= 0.75):
            Fact-checked DB evidence is trustworthy.  Trust bucket_a.label
            regardless of what the classifier says.
            confidence = min(0.90, similarity)

        Rule 2a — MODERATE BUCKET A (0.60–0.75) + CONFIDENT CLASSIFIER DISAGREES:
            Neither source is fully trustworthy alone.
            Output UNVERIFIED, confidence = 0.55.

        Rule 2b — MODERATE BUCKET A + CLASSIFIER AGREES or IS WEAK:
            Fact-check still outranks a weak/agreeing classifier.
            confidence = similarity * 0.85

        Rule 3a — NO BUCKET A, CLASSIFIER CONFIDENT (>= 0.90):
            No retrieved evidence at all.  Fall back to classifier, discounted.
            confidence = classifier_confidence * 0.70

        Rule 3b — NO BUCKET A, CLASSIFIER WEAK:
            Nothing to work with.
            Output UNVERIFIED, confidence = 0.50

        Args:
            bucket_a          : List of BucketAEntry dicts (may be empty).
            classifier_signal : System 1's raw output dict (may be None).
            verdict_signal    : Russell's retrieval signal string.  When
                                "LOW_CONFIDENCE", all rules are bypassed and
                                UNVERIFIED is returned immediately.

        Returns:
            A ``ConflictResolution`` named tuple.
        """
        # ── LOW_CONFIDENCE pre-check ─────────────────────────────────────
        # Russell's signal explicitly flags that his retrieval is unreliable.
        # We must not override this with bucket_a matches — a match found
        # under low-confidence retrieval may be a false positive.
        if verdict_signal == "LOW_CONFIDENCE":
            return ConflictResolution(
                verdict="UNVERIFIED",
                confidence=0.50,
                rule="no_evidence_clf_weak",
                reason=(
                    "Russell's retrieval signal is LOW_CONFIDENCE, indicating "
                    "the retrieved evidence is unreliable. Even though a "
                    "fact-check match exists, it cannot be trusted under low-"
                    "confidence retrieval. Verdict deferred to UNVERIFIED. "
                    "⚠️ Warning: Russell retrieved sparse evidence. "
                    "Treat this verdict with caution."
                ),
            )

        clf_label      = None
        clf_confidence = 0.0
        clf_verdict    = None

        if classifier_signal:
            clf_label      = classifier_signal.get("label", "")
            clf_confidence = float(classifier_signal.get("confidence", 0.0))
            clf_verdict    = "FALSE" if clf_label == "fake" else "TRUE"

        # ── Defensive suspicious_match filter ────────────────────────────
        # verdict_engine.decide() already filters these, but resolve_bucket_a_
        # conflict() may be called directly (tests, future callers). Drop any
        # suspicious_match==True entries so they never drive a verdict.
        if bucket_a:
            bucket_a = [e for e in bucket_a if not e.get("suspicious_match", False)]

        # ── Rules 1 & 2: bucket_a is present ────────────────────────────
        if bucket_a:
            best   = max(bucket_a, key=lambda x: x["similarity"])
            sim    = best["similarity"]
            a_verdict = _label_to_verdict(best["label"])
            source = best.get("source", "fact-check DB")

            # Rule 1 — solid bucket_a
            if sim >= _BUCKET_A_SOLID_THRESHOLD:
                confidence = round(min(0.90, sim), 4)
                reason = (
                    f"Russell found solid fact-checked evidence in known-fakes "
                    f"database (similarity {sim:.3f}, source: {source}). "
                    f"System 1 classifier disagreement is overridden because "
                    f"fact-checked evidence outranks classifier prediction."
                )
                return ConflictResolution(
                    verdict=a_verdict,
                    confidence=confidence,
                    rule="solid_bucket_a",
                    reason=reason,
                )

            # Rule 2 — moderate bucket_a (0.60 <= sim < 0.75)
            if sim >= _BUCKET_A_MODERATE_THRESHOLD:
                classifier_disagrees = (
                    clf_verdict is not None
                    and clf_verdict != a_verdict
                    and clf_confidence >= _CLASSIFIER_CHALLENGE_THRESHOLD
                )

                if classifier_disagrees:
                    # Rule 2a — conflict
                    reason = (
                        f"Moderate fact-checked evidence (similarity {sim:.3f}, "
                        f"source: {source}) conflicts with confident classifier "
                        f"prediction ({clf_label}, {clf_confidence:.3f}). "
                        f"Neither source is fully trustworthy alone."
                    )
                    return ConflictResolution(
                        verdict="UNVERIFIED",
                        confidence=0.55,
                        rule="moderate_conflict",
                        reason=reason,
                    )
                else:
                    # Rule 2b — agree or weak classifier
                    confidence = round(sim * 0.85, 4)
                    reason = (
                        f"Moderate fact-checked evidence (similarity {sim:.3f}, "
                        f"source: {source}) is the primary signal. "
                        f"Classifier is weak or agrees; fact-check outranks it."
                    )
                    return ConflictResolution(
                        verdict=a_verdict,
                        confidence=confidence,
                        rule="moderate_agree",
                        reason=reason,
                    )

            # bucket_a exists but similarity < 0.60 — too weak to trust alone;
            # fall through to Rule 3 logic using classifier as primary.

        # ── Rule 3: no usable bucket_a ───────────────────────────────────
        if clf_confidence >= _CLASSIFIER_CHALLENGE_THRESHOLD and clf_verdict:
            confidence = round(clf_confidence * 0.70, 4)
            reason = (
                "No retrieved evidence found in fact-check DB or trusted sources. "
                "Verdict relies solely on classifier prediction with reduced confidence."
            )
            return ConflictResolution(
                verdict=clf_verdict,
                confidence=confidence,
                rule="no_evidence_clf_strong",
                reason=reason,
            )

        # Rule 3b — nothing reliable
        return ConflictResolution(
            verdict="UNVERIFIED",
            confidence=0.50,
            rule="no_evidence_clf_weak",
            reason=(
                "No evidence retrieved and classifier confidence is low. "
                "Insufficient basis for verdict."
            ),
        )

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
                verdict                (str)   — "TRUE", "FALSE", or "UNVERIFIED"
                confidence             (float) — calibrated score in (0, 0.95]
                reasoning_summary      (str)   — compact debug string
                evidence_sparse        (bool)  — True when LOW_CONFIDENCE signal
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
        # is uncertain.  Three overrides apply:
        #
        #   a) low_confidence_penalty flag: always True under LOW_CONFIDENCE.
        #      The reason_builder reads this to prepend a warning.
        #
        #   b) Sparse evidence (< 3 evaluated propositions):
        #      Force verdict to UNVERIFIED — not enough data to decide.
        #
        #   c) Confidence multiplied by 0.75 — even strong, unanimous NLI
        #      evidence cannot overcome Russell's retrieval uncertainty.
        #      Applied AFTER the sparse check so UNVERIFIED cases also get
        #      the penalty (capped at 0.65 as before for sparse cases).
        # ----------------------------------------------------------------
        evidence_sparse         = False
        low_confidence_penalty  = False

        if verdict_signal == "LOW_CONFIDENCE":
            evidence_sparse        = True
            low_confidence_penalty = True
            total_evaluated        = len(stances)

            # Override (b): too few propositions → force UNVERIFIED
            if total_evaluated < 3:
                verdict = "UNVERIFIED"

            # Override (c): multiply by 0.75, then cap at 0.65
            confidence = min(confidence * 0.75, 0.65)

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
            f"evidence_sparse={evidence_sparse}, "
            f"low_confidence_penalty={low_confidence_penalty}"
        )

        return verdict, round(confidence, 4), reasoning_summary, evidence_sparse
