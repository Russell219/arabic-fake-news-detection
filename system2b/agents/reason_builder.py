"""
reason_builder.py — Human-readable explanation generator for the Verdict Engine.

Assembles a single coherent reason string from four parts:
    1. Signal context   — what Russell's retrieval found
    2. Bucket A mention — fact-check DB hit (if present)
    3. Bucket B summary — NLI stance counts over trusted propositions
    4. Verdict conclusion — one-line summary of the final decision

The output string is stored in ``FinalOutput.reason`` and is intended
for end-user display, logging, and audit trails.
"""

from typing import List, Optional

from agents.schemas import StanceDetail


class ReasonBuilder:
    """
    Builds the human-readable ``reason`` field of a ``FinalOutput``.

    Stateless — instantiate once, call ``build()`` as many times as needed.
    """

    # ------------------------------------------------------------------
    # Part 1: signal context strings
    # ------------------------------------------------------------------

    _SIGNAL_CONTEXT: dict[str, str] = {
        "HIGH_FAKE_MATCH":
            "Russell found a high-similarity match in the known-fakes database.",
        "HIGH_TRUE_MATCH":
            "Russell found a high-similarity match in the known-fakes database.",
        "HIGH_PARTIAL_MATCH":
            "Russell found a partial match in the known-fakes database.",
        "POSSIBLE_FAKE":
            "Russell flagged this as possibly fake, with related evidence retrieved.",
        "POSSIBLE_TRUE":
            "Russell flagged this as possibly true, with supporting evidence retrieved.",
        "POSSIBLE_MATCH":
            "Russell found a possible match; evidence is ambiguous.",
        "EVIDENCE_FOUND":
            "Russell found relevant evidence in the knowledge base.",
        "LOW_CONFIDENCE":
            "Russell returned low confidence; evidence is sparse.",
    }

    # ------------------------------------------------------------------
    # Part 4: verdict conclusion strings
    # ------------------------------------------------------------------

    _VERDICT_CONCLUSION: dict[str, str] = {
        "FALSE":       "The evidence strongly contradicts the claim.",
        "TRUE":        "The evidence consistently supports the claim.",
        "UNVERIFIED":  "Evidence is insufficient or contradictory; verdict is uncertain.",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        verdict: str,
        verdict_signal: str,
        bucket_a_present: bool,
        bucket_a_similarity: float,
        bucket_a_source: str,
        bucket_a_debunk: str,
        stance_breakdown: List[StanceDetail],
        evidence_sparse: bool = False,
    ) -> str:
        """
        Construct a human-readable reason string for a final verdict.

        Args:
            verdict             : "TRUE", "FALSE", or "UNVERIFIED".
            verdict_signal      : Russell's retrieval signal string.
            bucket_a_present    : Whether a Bucket A entry was used.
            bucket_a_similarity : Similarity score of the Bucket A hit (used
                                  only when ``bucket_a_present`` is True).
            bucket_a_source     : Source name of the Bucket A hit.
            bucket_a_debunk     : Debunking text / URL from the Bucket A hit.
            stance_breakdown    : List of ``StanceDetail`` dicts from NLI path
                                  (may be empty for Path 1).
            evidence_sparse     : When True, a ⚠️ warning is appended alerting
                                  the consumer that Russell's retrieval was
                                  low-confidence and the verdict is unreliable.

        Returns:
            A single concatenated reason string.
        """
        parts: list[str] = []

        # Part 1 — Signal context
        parts.append(self._build_signal_context(verdict_signal))

        # Part 2 — Bucket A mention (conditional)
        if bucket_a_present:
            parts.append(
                self._build_bucket_a_mention(
                    bucket_a_similarity,
                    bucket_a_source,
                    bucket_a_debunk,
                )
            )

        # Part 3 — Bucket B stance summary
        parts.append(self._build_stance_summary(stance_breakdown))

        # Part 4 — Verdict conclusion
        parts.append(self._build_verdict_conclusion(verdict))

        # Part 5 — Sparse evidence warning (LOW_CONFIDENCE path only)
        if evidence_sparse:
            parts.append(
                "⚠️ Warning: Russell retrieved sparse evidence. "
                "Treat this verdict with caution."
            )

        return " ".join(parts)

    def build_conflict_resolution(
        self,
        rule: str,
        verdict: str,
        bucket_a_similarity: float,
        bucket_a_source: str,
        clf_label: Optional[str],
        clf_confidence: float,
        base_reason: str,
    ) -> str:
        """
        Build a human-readable reason string for conflict-resolution verdicts.

        Called when bucket_b is empty and the verdict was determined by
        ``StanceAggregator.resolve_bucket_a_conflict()``.

        Args:
            rule               : The rule key from ConflictResolution.rule.
            verdict            : Final verdict string.
            bucket_a_similarity: Similarity of the best Bucket A hit (0 if absent).
            bucket_a_source    : Source of the best Bucket A hit ("" if absent).
            clf_label          : Classifier label ("real"/"fake", or None).
            clf_confidence     : Classifier confidence score.
            base_reason        : The reason string already produced by the
                                 aggregator (used as the core explanation).

        Returns:
            A single formatted reason string.
        """
        # The aggregator already computes a precise reason string per rule.
        # Here we prepend a one-line summary tag for quick scanning in logs.
        rule_tag = {
            "solid_bucket_a":       "[Rule 1 — Solid Bucket A]",
            "moderate_conflict":    "[Rule 2a — Moderate Conflict]",
            "moderate_agree":       "[Rule 2b — Moderate + Agree]",
            "no_evidence_clf_strong": "[Rule 3a — Classifier Only]",
            "no_evidence_clf_weak": "[Rule 3b — No Evidence]",
        }.get(rule, "[Conflict Resolution]")

        verdict_tag = self._VERDICT_CONCLUSION.get(
            verdict, "The verdict could not be determined."
        )

        return f"{rule_tag} {base_reason} {verdict_tag}"

    # ------------------------------------------------------------------
    # Private part builders
    # ------------------------------------------------------------------

    def _build_signal_context(self, verdict_signal: str) -> str:
        """Return the Part 1 signal-context sentence."""
        return self._SIGNAL_CONTEXT.get(
            verdict_signal,
            "Russell returned an unrecognised signal.",
        )

    def _build_bucket_a_mention(
        self,
        similarity: float,
        source: str,
        debunk: str,
    ) -> str:
        """Return the Part 2 Bucket A sentence."""
        return (
            f"A related debunked claim was found "
            f"(similarity {similarity:.2f} from {source})."
        )

    def _build_stance_summary(self, stance_breakdown: List[StanceDetail]) -> str:
        """
        Return the Part 3 Bucket B stance-summary sentence.

        Counts SUPPORTS, REFUTES, and NEUTRAL entries and picks the
        appropriate template.
        """
        if not stance_breakdown:
            return "No relevant propositions were retrieved."

        n_support = sum(1 for sd in stance_breakdown if sd["stance"] == "SUPPORTS")
        n_refute  = sum(1 for sd in stance_breakdown if sd["stance"] == "REFUTES")
        n_neutral = sum(1 for sd in stance_breakdown if sd["stance"] == "NEUTRAL")
        total     = len(stance_breakdown)

        # All refute, no support
        if n_refute > 0 and n_support == 0:
            return (
                f"All {total} retrieved propositions from trusted sources "
                f"refute this claim."
            )

        # All support, no refute
        if n_support > 0 and n_refute == 0:
            return (
                f"All {total} retrieved propositions from trusted sources "
                f"support this claim."
            )

        # Mixed support and refute
        if n_support > 0 and n_refute > 0:
            return (
                f"Mixed evidence: {n_refute} refutes, "
                f"{n_support} supports, {n_neutral} neutral."
            )

        # Only neutral (both n_support and n_refute are 0)
        return (
            f"Retrieved evidence is neutral ({n_neutral} propositions); "
            f"no clear stance detected."
        )

    def _build_verdict_conclusion(self, verdict: str) -> str:
        """Return the Part 4 verdict-conclusion sentence."""
        return self._VERDICT_CONCLUSION.get(
            verdict,
            "The verdict could not be determined.",
        )
