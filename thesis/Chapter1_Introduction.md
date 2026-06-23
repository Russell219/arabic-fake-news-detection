# Chapter 1: Introduction

## 1.1 Problem Statement

The rapid spread of misinformation on Arabic-language social media and news platforms poses a significant challenge to public trust and informed decision-making. Unlike English, Arabic fake news detection suffers from two compounding problems: (1) a scarcity of large-scale, continuously updated, labeled fact-checking resources, and (2) the linguistic complexity of Arabic, including dialectal variation (Modern Standard Arabic vs. Egyptian, Gulf, and other colloquial dialects), which degrades the performance of standard NLP pipelines trained primarily on MSA text.

Existing automated fact-checking systems for Arabic typically rely on static knowledge bases that become outdated as real-world events unfold, and most provide a single classification label without retrievable, traceable evidence to support their verdict. This creates two key gaps: claims about recent events cannot be verified against current information, and end users have no way to audit *why* a system reached a particular verdict.

This project addresses these gaps through a hybrid multi-agent framework that combines machine learning classification, retrieval-augmented fact verification, and a verdict validation layer — producing not just a verdict, but evidence and source traceability for every claim submitted.

## 1.2 Project Objectives

1. Build a multi-stage hybrid AI framework capable of classifying Arabic claims as **TRUE**, **FALSE**, or **UNVERIFIED**.
2. Implement a Retrieval-Augmented Generation (RAG) fact-verification engine that retrieves supporting or contradicting evidence from both a curated fact-checked claims database and a continuously updated live news knowledge base.
3. Ensure the system handles dialectal Arabic input (MSA, Egyptian, Gulf, and others) without requiring separate models per dialect.
4. Maintain knowledge base freshness through incremental ingestion from live RSS news sources, eliminating the "stale knowledge" problem identified in prior fact-checking literature.
5. Provide every verdict with retrievable, source-linked evidence to support transparency and auditability.
6. Achieve measurable retrieval precision (target: Precision@1 ≥ 0.85) on a held-out evaluation set of labeled Arabic claims.

## 1.3 Motivation and Significance

**Academic motivation:** Recent peer-reviewed work on Arabic fact verification — notably VERIFAID (Lopez-Joya et al., 2025) — explicitly lists continuous knowledge base updating as unsolved future work. This project directly implements that gap, contributing a working incremental ingestion pipeline as a novel extension to the existing literature. Separately, FreshLLMs (Vu et al., 2023) demonstrated that large language models fail systematically on fast-changing factual queries; this project adopts the complementary strategy of pre-ingesting fresh evidence into a retrieval index rather than relying on query-time web search, making verification auditable and reproducible.

**Practical/market motivation:** Arabic-speaking regions face disproportionate exposure to health, political, and crisis misinformation (e.g., COVID-19 origin claims, conflict-related claims), while commercial fact-checking tools targeting Arabic remain limited compared to English-language equivalents (e.g., Full Fact, Snopes). A system that combines classification speed with evidence-backed verification addresses a real, underserved need.

## 1.4 Scope and Limitations

**In scope:**
- Arabic-language claims only, spanning Modern Standard Arabic and major dialects (Egyptian, Gulf, Levantine).
- Three-stage pipeline: ML-based initial classification → RAG-based evidence retrieval and verdict scoring → verdict cross-validation.
- Knowledge base composed of: (a) ~18,600 labeled fact-checked claims from AraFacts, (b) ~3,000 scraped and labeled articles from Saheeh Masr, and (c) 28,800+ propositions extracted from 2,000+ news articles across 7 live RSS sources, updated automatically every 4 hours.
- Sentence-level proposition retrieval with context-aware decontextualization, hybrid retrieval (BM25 + multilingual E5-large embeddings combined via Reciprocal Rank Fusion), and cross-encoder re-ranking.

**Limitations:**
- The system is restricted to text-based claims; image, video, and audio-based misinformation are out of scope.
- Knowledge base coverage is limited to the 7 RSS sources selected for domain diversity (politics, economy, health, science, sports); claims about topics outside these domains may be returned as UNVERIFIED due to lack of evidence, not necessarily because the claim is false.
- Dialect detection is a soft signal used for display and query handling; misclassification does not block retrieval, since the underlying retrieval is based on semantic embeddings rather than dialect-specific rules.
- The verdict validation stage (System 3) is owned by a separate team member and integrated via a defined JSON contract; end-to-end accuracy depends on that integration being completed and tested jointly.

## 1.5 Team Members' Contributions

| Member | Role/Responsibility |
|---|---|
| Sarah | **System 1 — ML Classification.** Built and trained the machine learning classifier that performs an initial pass on the submitted claim, producing a preliminary fake/real signal with an associated confidence score, passed downstream to System 2. |
| Russell | **System 2 — RAG Fact-Verification Engine.** Designed and implemented the retrieval-augmented verification pipeline: dialect detection, query reformulation, hybrid retrieval (BM25 + E5-large + RRF), cross-encoder re-ranking, CRAG-style confidence gating, and the live incremental knowledge base update pipeline (7 RSS sources, automated 4-hour refresh cycle). Built the Gradio-based testing interface and defined the system's output contract for downstream integration. |
| Youssef | **System 3 — Verdict Validation.** Built the verdict cross-checking layer that consumes System 2's output (verdict signal, confidence, retrieved evidence) and produces the final validated decision, acting as a safeguard against over-confident or evidence-weak verdicts. |

*(Each member is also responsible for writing the chapters/sections covering their own system in Chapters 5–8, with this Introduction and Literature Review written jointly.)*
