"""
schemas.py — Type contracts for the Verdict Engine (Cyber Teammate).

This module defines the full input/output surface of the Verdict Engine:
  - INPUT:  Russell's RAG output (RussellOutput), including two evidence buckets.
  - OUTPUT: The Final Verdict emitted by this engine (FinalOutput).

No logic lives here — only structural type definitions.
"""

from typing import TypedDict, List, Literal


# ---------------------------------------------------------------------------
# INPUT CONTRACT — Russell's RAG Engine Output
# ---------------------------------------------------------------------------

class BucketAEntry(TypedDict):
    """
    A single entry from Bucket A: the Known-Fakes / Fact-Check database.

    Bucket A is queried first. Each entry represents a previously fact-checked
    claim that is semantically similar to the incoming claim.

    Fields:
        claim       : The archived claim text as stored in the fact-check DB.
        similarity  : Cosine (or equivalent) similarity score in [0, 1].
        label       : The ground-truth verdict assigned by human fact-checkers.
        source      : The fact-checking organisation or outlet (e.g. "Misbar").
        debunk      : A short debunking explanation or URL provided by the source.
    """

    claim: str
    similarity: float
    label: Literal["TRUE", "FALSE", "PARTIALLY_TRUE"]
    source: str
    debunk: str


class BucketBEntry(TypedDict):
    """
    A single entry from Bucket B: verified propositions from trusted news sources.

    Bucket B is used when Bucket A does not yield a high-confidence match.
    Each entry is a proposition retrieved via hybrid search (BM25 + AraBERT).

    Fields:
        proposition   : The extracted proposition text from the trusted source.
        title         : Headline or title of the source article.
        source        : The trusted outlet or wire service (e.g. "Reuters AR").
        hybrid_score  : Combined retrieval score (BM25 + AraBERT), in [0, 1].
        bm25_score    : Lexical BM25 component of the hybrid score.
        arabert_score : Semantic AraBERT component of the hybrid score.
    """

    proposition: str
    title: str
    source: str
    hybrid_score: float
    bm25_score: float
    arabert_score: float


class RussellOutput(TypedDict):
    """
    The full JSON payload produced by Russell's RAG engine.

    This is the sole input to the Verdict Engine. It contains the original
    claim, dialect metadata, a verdict signal summarising retrieval confidence,
    and two evidence buckets for downstream reasoning.

    Fields:
        claim               : The original Arabic claim being investigated.
        dialect             : Detected Arabic dialect — Cairo colloquial or MSA.
        dialect_confidence  : Confidence of the dialect classifier, in [0, 1].
        query_used          : The (possibly normalised/translated) query sent
                              to the retrieval engines.
        verdict_signal      : A categorical signal encoding retrieval confidence:
                                - HIGH_FAKE_MATCH   → strong Bucket A fake hit
                                - HIGH_TRUE_MATCH   → strong Bucket A true hit
                                - HIGH_PARTIAL_MATCH→ strong but partial hit
                                - POSSIBLE_FAKE     → moderate fake signal
                                - POSSIBLE_TRUE     → moderate true signal
                                - POSSIBLE_MATCH    → moderate, ambiguous
                                - EVIDENCE_FOUND    → Bucket B has evidence
                                - LOW_CONFIDENCE    → weak or no retrieval hits
        bucket_a            : List of fact-checked claim matches (may be empty).
        bucket_b            : List of trusted-source propositions (may be empty).
        bucket_b_searched   : Whether Bucket B was queried during this run.
    """

    claim: str
    dialect: Literal["CAI", "MSA"]
    dialect_confidence: float
    query_used: str
    verdict_signal: Literal[
        "HIGH_FAKE_MATCH",
        "HIGH_TRUE_MATCH",
        "HIGH_PARTIAL_MATCH",
        "POSSIBLE_FAKE",
        "POSSIBLE_TRUE",
        "POSSIBLE_MATCH",
        "EVIDENCE_FOUND",
        "LOW_CONFIDENCE",
    ]
    bucket_a: List[BucketAEntry]
    bucket_b: List[BucketBEntry]
    bucket_b_searched: bool


# ---------------------------------------------------------------------------
# OUTPUT CONTRACT — Verdict Engine Final Output
# ---------------------------------------------------------------------------

class StanceDetail(TypedDict):
    """
    The NLI stance result for a single Bucket B proposition.

    Produced during Path 2 (NLI path) for every proposition in bucket_b.
    Collected into a list that forms the stance_breakdown of FinalOutput.

    Fields:
        evidence : The proposition text that was evaluated against the claim.
        stance   : NLI label collapsed to three categories:
                     - SUPPORTS → entailment
                     - REFUTES  → contradiction
                     - NEUTRAL  → neutral
        score    : The hybrid_score-weighted NLI confidence for this stance,
                   in [0, 1]. Used when aggregating the final verdict.
    """

    evidence: str
    stance: Literal["SUPPORTS", "REFUTES", "NEUTRAL"]
    score: float


class FinalOutput(TypedDict):
    """
    The final structured verdict emitted by the Verdict Engine.

    This is the engine's sole output, consumed by downstream components
    (e.g. the presentation layer or an orchestrating agent).

    Fields:
        final_verdict    : The top-level verdict:
                             - TRUE        → claim is supported by evidence
                             - FALSE       → claim is refuted by evidence
                             - UNVERIFIED  → insufficient or conflicting evidence
        confidence       : Aggregated confidence in the final_verdict, in [0, 1].
                           For Path 1 this is the Bucket A similarity score;
                           for Path 2 it is the weighted NLI aggregate.
        stance_breakdown : Per-proposition NLI details (Path 2 only).
                           Empty list when Path 1 is taken.
        reason           : Human-readable explanation of how the verdict was
                           reached, including which path was taken and why.
    """

    final_verdict: Literal["TRUE", "FALSE", "UNVERIFIED"]
    confidence: float
    stance_breakdown: List[StanceDetail]
    reason: str
