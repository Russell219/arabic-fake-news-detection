"""
schemas.py — Type contracts for the Verdict Engine (Cyber Teammate).

This module defines the full input/output surface of the Verdict Engine:
  - INPUT:  Russell's RAG output (RussellOutput), including two evidence buckets
            and System 1's (Sarah's) classifier signal as a pass-through field.
  - OUTPUT: The Final Verdict emitted by this engine (FinalOutput).

Schema version: v2 — aligned with Russell's updated output_schema.json
Key changes from v1:
  - BucketAEntry.label expanded (PARTLY_FALSE, SARCASM, UNVERIFIABLE, UNKNOWN)
  - BucketAEntry.dialect added (optional)
  - BucketBEntry: bm25_score/arabert_score → bm25_rank/e5_rank (integer ranks);
    hybrid_score kept (RRF value); rerank_score added as primary weight field;
    proposition_display added (optional, decontextualized top hit)
  - RussellOutput.dialect now open str (dialect model supports DOH, EGY, etc.)
  - RussellOutput gains: final_verdict, confidence, classifier_signal
  - New ClassifierSignal TypedDict (System 1 pass-through)

No logic lives here — only structural type definitions.
"""

from typing import TypedDict, List, Literal, Optional


# ---------------------------------------------------------------------------
# INPUT CONTRACT — Russell's RAG Engine Output
# ---------------------------------------------------------------------------

class BucketAEntry(TypedDict, total=False):
    """
    A single entry from Bucket A: the Known-Fakes / Fact-Check database
    (AraFacts + Saheeh Masr).

    Fields:
        claim       : The archived claim text as stored in the fact-check DB.
        similarity  : Cosine similarity score in [0, 1].
        label       : The ground-truth verdict assigned by human fact-checkers.
                      Expanded in v2:
                        TRUE         → confirmed true
                        FALSE        → confirmed false
                        PARTLY_FALSE → partially false (replaces PARTIALLY_TRUE)
                        SARCASM      → satirical/sarcastic content
                        UNVERIFIABLE → cannot be verified
                        UNKNOWN      → label not available
        source      : The fact-checking organisation (e.g. "Misbar", "AFP").
        dialect     : Detected dialect of the archived claim (optional;
                      empty string for non-dialectal sources).
        debunk      : Debunking text truncated to 200 chars.
                      IMPORTANT: saheeh_masr entries often have an empty string
                      here — this is not evidence of anything; check 'source'.
    """

    # required fields
    claim: str
    similarity: float
    label: Literal["TRUE", "FALSE", "PARTLY_FALSE", "SARCASM", "UNVERIFIABLE", "UNKNOWN"]
    source: str
    # optional fields (total=False covers the whole class; required ones are
    # enforced at runtime via Russell's schema, not Python's type system)
    dialect: str
    debunk: str


class BucketBEntry(TypedDict, total=False):
    """
    A single entry from Bucket B: propositions from the live news knowledge
    base (28,800+ propositions, 7 RSS sources, auto-updated every 4 h).

    Retrieval upgraded in v2: AraBERT weighted-sum → E5-large + RRF fusion.

    Fields:
        proposition         : The extracted proposition text.
        proposition_display : Decontextualized version (optional; only present
                              on the top-ranked hit; falls back to proposition).
        title               : Headline of the source article.
        source              : Trusted outlet key (e.g. "BBC_Arabic").
        hybrid_score        : RRF fusion score (BM25 rank + E5 rank).
                              Typical range ~0.005–0.04.
                              NOT a [0,1] confidence — do NOT use as weight.
        bm25_rank           : 1-based BM25 rank (lower = better). NOT a score.
        e5_rank             : 1-based E5-large embedding rank. NOT a score.
        rerank_score        : Cross-encoder relevance score.
                              Typical range ~-8 to +10.
                              F1-calibrated threshold for real evidence: > 2.0.
                              THIS is the recommended field for evidence weighting.
    """

    # required fields
    proposition: str
    title: str
    source: str
    hybrid_score: float
    bm25_rank: int
    e5_rank: int
    rerank_score: float
    # optional
    proposition_display: str


class ClassifierSignal(TypedDict, total=False):
    """
    System 1 (Sarah's) raw classifier output, passed through by Russell
    unmodified.  Fusion with Russell's verdict happens HERE in System 3,
    not in System 2.

    Fields:
        label        : "real" or "fake" (lowercase).
        label_id     : 0 = real, 1 = fake.
        confidence   : Classifier confidence in the predicted label, [0, 1].
        probabilities: Per-class probability dict {"real": float, "fake": float}.
    """

    label: Literal["real", "fake"]
    label_id: Literal[0, 1]
    confidence: float
    probabilities: dict   # {"real": float, "fake": float}


class RussellOutput(TypedDict, total=False):
    """
    The full JSON payload produced by Russell's RAG engine (v2 schema).

    This is the sole input to the Verdict Engine. It carries the original claim,
    dialect metadata, retrieval signals, two evidence buckets, Russell's own
    preliminary verdict, and System 1's classifier signal for fusion.

    Fields:
        claim               : The original Arabic claim being investigated.
        dialect             : Detected Arabic dialect code — open string;
                              the CAMeL-Lab model supports MSA, CAI, DOH, etc.
        dialect_confidence  : Confidence of the dialect classifier, [0, 1].
        query_used          : The (possibly normalised) query sent to retrieval.
        verdict_signal      : Categorical retrieval-confidence signal:
                                HIGH_FAKE_MATCH    → strong Bucket A fake hit
                                HIGH_TRUE_MATCH    → strong Bucket A true hit
                                HIGH_PARTIAL_MATCH → strong but partial hit
                                POSSIBLE_FAKE      → moderate fake signal
                                POSSIBLE_TRUE      → moderate true signal
                                POSSIBLE_MATCH     → moderate, ambiguous
                                EVIDENCE_FOUND     → Bucket B has evidence
                                LOW_CONFIDENCE     → weak or no retrieval hits
        final_verdict       : Russell's own preliminary verdict (NEW in v2).
                              System 3 may agree, override, or fuse this.
        confidence          : Russell's confidence in his own final_verdict.
        bucket_a            : Fact-check DB matches (may be empty).
        bucket_b            : Trusted-source propositions (may be empty).
        bucket_b_searched   : False only when a HIGH-tier Bucket A match
                              short-circuited the pipeline.
        classifier_signal   : System 1's raw output (pass-through, nullable).
    """

    # required
    claim: str
    dialect: str                  # open string — not limited to CAI/MSA
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
    final_verdict: Literal["TRUE", "FALSE", "UNVERIFIED"]
    confidence: float
    bucket_a: List[BucketAEntry]
    bucket_b: List[BucketBEntry]
    bucket_b_searched: bool
    # optional
    classifier_signal: Optional[ClassifierSignal]


# ---------------------------------------------------------------------------
# OUTPUT CONTRACT — Verdict Engine Final Output
# ---------------------------------------------------------------------------

class StanceDetail(TypedDict):
    """
    The NLI stance result for a single Bucket B proposition.

    Produced during Path 2 (NLI path) for every proposition in bucket_b
    whose rerank_score passes the quality threshold (> 2.0).

    Fields:
        evidence      : "{title} ({source})" — the proposition context string.
        stance        : NLI label collapsed to three categories:
                          SUPPORTS → entailment
                          REFUTES  → contradiction
                          NEUTRAL  → neutral
        score         : rerank_score-derived weight for this stance, normalised
                        to [0, 1].  Used in aggregation.
        rerank_score  : Raw cross-encoder score from Russell (for transparency).
    """

    evidence: str
    stance: Literal["SUPPORTS", "REFUTES", "NEUTRAL"]
    score: float
    rerank_score: float


class FinalOutput(TypedDict):
    """
    The final structured verdict emitted by the Verdict Engine.

    Consumed by downstream components (presentation layer, orchestrator).

    Fields:
        final_verdict      : The fused top-level verdict:
                               TRUE       → claim is supported by evidence
                               FALSE      → claim is refuted by evidence
                               UNVERIFIED → insufficient or conflicting evidence
        confidence         : Aggregated confidence in final_verdict, in [0, 1].
        stance_breakdown   : Per-proposition NLI details (Path 2 only).
                             Empty list when Path 1 is taken.
        reason             : Human-readable explanation of how the verdict was
                             reached, including which path and fusion logic used.
        classifier_fusion  : Dict summarising how System 1's signal was used:
                               {"used": bool, "label": str, "confidence": float,
                                "effect": "reinforced"|"overridden"|"ignored"|"absent"}
    """

    final_verdict: Literal["TRUE", "FALSE", "UNVERIFIED"]
    confidence: float
    stance_breakdown: List[StanceDetail]
    reason: str
    classifier_fusion: dict
