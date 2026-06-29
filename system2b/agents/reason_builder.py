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
        low_confidence_detected: bool = False,
    ) -> str:
        """
        Construct a human-readable reason string for a final verdict.

        Args:
            verdict                 : "TRUE", "FALSE", or "UNVERIFIED".
            verdict_signal          : Russell's retrieval signal string.
            bucket_a_present        : Whether a Bucket A entry was used.
            bucket_a_similarity     : Similarity score of the Bucket A hit.
            bucket_a_source         : Source name of the Bucket A hit.
            bucket_a_debunk         : Debunking text from the Bucket A hit.
            stance_breakdown        : List of StanceDetail dicts (may be empty).
            evidence_sparse         : When True, a warning is appended for
                                      LOW_CONFIDENCE sparse evidence.
            low_confidence_detected : When True AND no solid bucket_a (sim <
                                      0.75), a ⚠️ LOW_CONFIDENCE warning is
                                      prepended to the reason string.  Never
                                      silently passes low confidence through.

        Returns:
            A single concatenated reason string.
        """
        parts: list[str] = []

        # Part 0 — LOW_CONFIDENCE warning prefix (when no solid bucket_a).
        # Only prepended here for Path 2 (NLI path).  The dedicated
        # _path_low_confidence() in verdict_engine.py handles the non-NLI cases
        # directly without going through build().
        solid_bucket_a = bucket_a_present and bucket_a_similarity >= 0.75
        if low_confidence_detected and not solid_bucket_a:
            parts.append(
                "⚠️ Low retrieval confidence reported by RAG engine."
            )

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

        The conclusion sentence is chosen based on RULE, not on verdict alone.
        This prevents the contradiction where Rule 1 (solid evidence) fires but
        the generic UNVERIFIED conclusion says "insufficient or contradictory".

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
        rule_tag = {
            "solid_bucket_a":         "[Rule 1 — Solid Bucket A]",
            "moderate_conflict":      "[Rule 2a — Moderate Conflict]",
            "moderate_agree":         "[Rule 2b — Moderate + Agree]",
            "no_evidence_clf_strong": "[Rule 3a — Classifier Only]",
            "no_evidence_clf_weak":   "[Rule 3b — No Evidence]",
        }.get(rule, "[Conflict Resolution]")

        # --- Choose conclusion based on RULE, not verdict ---
        # Rule 1: solid bucket_a drove the verdict — conclusion must reflect
        # the fact-check DB finding, NOT the generic UNVERIFIED sentence.
        if rule == "solid_bucket_a":
            verdict_direction = (
                "the claim is FALSE (refuted by fact-checkers)"
                if verdict == "FALSE"
                else "the claim is TRUE (confirmed by fact-checkers)"
                if verdict == "TRUE"
                else "the claim could not be fully verified"
            )
            conclusion = (
                f"The fact-checked evidence from {bucket_a_source} strongly "
                f"indicates {verdict_direction}."
            )

        # Rule 2a: genuine conflict — UNVERIFIED is correct and the conclusion
        # should explain WHY it is uncertain (two sources disagree).
        elif rule == "moderate_conflict":
            conclusion = (
                "Neither the fact-check DB nor the classifier alone is "
                "sufficient; the verdict remains uncertain pending stronger evidence."
            )

        # Rule 2b: moderate bucket_a outranks weak/agreeing classifier.
        elif rule == "moderate_agree":
            verdict_direction = (
                "contradicts the claim" if verdict == "FALSE"
                else "supports the claim" if verdict == "TRUE"
                else "is inconclusive"
            )
            conclusion = (
                f"The fact-checked evidence from {bucket_a_source} "
                f"{verdict_direction}."
            )

        # Rule 3a: no retrieved evidence; classifier is the only signal.
        elif rule == "no_evidence_clf_strong":
            conclusion = (
                "No retrieved evidence is available; verdict is based solely "
                "on the classifier prediction at reduced confidence."
            )

        # Rule 3b: nothing reliable at all.
        else:
            conclusion = (
                "Evidence is insufficient or contradictory; "
                "verdict is uncertain."
            )

        return f"{rule_tag} {base_reason} {conclusion}"

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
