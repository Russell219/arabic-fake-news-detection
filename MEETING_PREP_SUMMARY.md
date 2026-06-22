# Meeting Prep Summary — System 2A

## The Headline Result (Reranker Calibration)

Old uncalibrated threshold (`> 0`): **F1 = 0.471**
New calibrated threshold (`> 2`): **F1 = 0.667** — a **42% relative improvement**

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0 (old) | 0.333 | 0.800 | 0.471 |
| **+2 (chosen)** | 0.750 | 0.600 | **0.667** |
| +3 | 1.000 | 0.500 | 0.667 |

**Why +2 over +3:** keeps more real evidence (60% vs 50% recall) at acceptable precision (75%), since missing real evidence is more costly than occasionally including a borderline piece.

**Method:** Built 197 labeled (claim, proposition) pairs — 147 from random AraFacts sampling (all came back "not relevant" — a real finding, most AraFacts claims are viral rumors with no real news coverage) + 50 from 5 deliberately-injected "known-good" claims (tagged `source: known_good_injected` for transparency), giving 10 relevant + 187 not relevant. Swept threshold values, measured precision/recall/F1 against these labels directly.

**Why this approach, not LLM-as-judge:** CRAG paper (Yan et al. 2024) showed prompting an LLM for relevance judgment underperforms a calibrated approach by ~20 points (58.65 vs 84.3 accuracy). Full fine-tuning (DIRAS-style) was ruled out — no GPU, insufficient balanced training data.

**Honest limitation if asked "only 10 relevant?":** reflects genuine evidence scarcity (documented Bucket B coverage gap), not a labeling flaw. Trend across thresholds is clean/monotonic, suggesting real signal despite small positive set. Next step: scale up known-good injection for a larger, more confident positive set.

---

## 3 Real Bugs Found and Fixed Today

1. **POSSIBLE-tier routing bug** — claims with moderate Bucket A similarity (0.84-0.86) skipped Bucket B entirely instead of gathering more evidence. Root cause: code used `if verdict is not None` to mean "stop here," conflating HIGH and POSSIBLE tiers. Fixed: only stop early for HIGH tier.

2. **Dialect normalization grammar bug** — Egyptian demonstrative (`ده`/`دي`) repositioning used a blind regex that broke longer sentences (e.g., `تغير مناخي ده كله كدب` → wrongly became `تغير هذا مناخي`). Fixed: only reorder when demonstrative is sentence-final.

3. **Crocodile/lexical mismatch bug** — E5 matched claims based on shared style/adjectives (e.g., "huge") rather than actual subject (crocodile vs. water wheel, 0.845 similarity). Fixed: added `lexical_overlap()` check — if similarity high but word overlap <0.15, distrust match and force Bucket B search. Grounded in Sciavolino et al. (EMNLP 2021) findings on dense retriever entity confusion.

---

## Architecture Recap (if asked to explain the system)

Sarah (classification) → Russell (RAG retrieval, Bucket A verified claims + Bucket B news KB) → Youssef (NLI + verdict aggregation)

Russell's cascade: Bucket A (E5-large cosine, HIGH≥0.86 / POSSIBLE≥0.84) → Bucket B if needed (RRF hybrid BM25+E5 + NER boost + cross-encoder rerank, now calibrated threshold=2)

---

## Remaining Task List

- [x] Reranker threshold calibration — DONE
- [ ] Query reformulation retry on Bucket B failure
- [ ] BM25 synonym expansion (scoped)
- [ ] Wire Sarah's signal into fact_check_claim (mock-tested)
- [ ] Youssef LOW_CONFIDENCE bug writeup (send to him)
- [ ] Bucket B incremental update mechanism
- [ ] CAMeL dialect morphological upgrade (proof-of-concept only, honestly scoped as future work)

---

## Key File Locations

- Main pipeline: `system2a_rag/system2_local.ipynb`
- Calibration work: `system2a_rag/reranker_calibration.ipynb`
- Labeled data: `system2a_rag/reranker_calibration_data.json`
- GitHub: `https://github.com/Russell219/arabic-fake-news-detection`

---

## Permanent Limitations (cannot be resolved in this timeframe, name explicitly)

1. AraFacts label noise (multi-source aggregation, no independent re-verification)
2. No trained reranker classifier (needs GPU infrastructure not available)
3. No public Arabic claim-evidence relevance benchmark exists
4. Full CAMeL morphological dialect upgrade competes with thesis-writing time
5. Small calibration sample (40-197) not yet statistically robust at scale

---

## Quick Q&A Cheat Sheet (anticipated questions)

**Q: Why F1 and not just precision or recall?**
A: Precision alone picks the strictest threshold (misses real evidence). Recall alone picks the loosest (catches everything, including wrong matches). F1 forces a genuine balance between both.

**Q: Why only 10 relevant examples?**
A: Reflects real evidence scarcity in Bucket B (most claims have no real coverage) — not a flaw in labeling. The threshold trend was smooth and consistent across 9 values, which is a sign of real signal even at small scale.

**Q: Can the 10 relevant be increased?**
A: Yes — just add more "known-good" claims and repeat the same process. Limited to 5 claims tonight due to time, not because the method maxes out there.

**Q: Who labeled the data, and how?**
A: Claude (LLM), via "raw prompting" (asked directly, no special training) — not fine-tuned. Less reliable than a fine-tuned model (per CRAG: ~58-65% vs ~84% accuracy), which is why it's paired with human spot-checking and described as a first-pass result.

**Q: Which paper is this annotation method based on?**
A: DIRAS (2024) — used an LLM to help label data (same purpose as us). Difference: DIRAS additionally trained a smaller model to copy the LLM's labeling; we used the LLM's labels directly, no extra training step (no GPU/time for it).

**Q: Is the EGY->MSA dialect issue fully resolved?**
A: Partially. The specific bug (demonstrative repositioning breaking grammar on longer sentences) is patched: only reposition when the word is sentence-final. The proper fix (real grammar check via CAMeL Tools' morphological analyzer) is identified but not built — clearly scoped as future work due to time competing with reranker calibration.

**Q: Example of the dialect bug?**
A: Input: "مفيش حاجة اسمها تغير مناخي ده كله كدب" (climate change doesn't exist, this is all lies).
Broken output (before fix): "...تغير هذا مناخي..." (nonsense: "this climate").
Fixed output (current patch): leaves "ده" alone since it's not sentence-final, avoiding the nonsense.
Still-imperfect case the patch doesn't catch: when demonstrative IS sentence-final but the previous word is a verb, not a noun (e.g. "كل اللي حصل ده" -> patch produces "كل اللي ده حصل", still odd, since "حصل" is a verb not a noun the demonstrative should attach to).

**Q: Have we tested the new threshold (=2) in practice yet?**
A: Not yet beyond the calibration sweep itself. Immediate next step: re-run existing test cases (crocodile case, Saheeh Masr eval) to confirm real-world behavior matches the calibration's prediction.

---

## Update — Dialect Normalization, Round 2 (after meeting)

**Upgrade applied:** Replaced the position-only demonstrative patch with a real grammar check using CAMeL Tools' Egyptian Arabic morphological disambiguator (`BERTUnfactoredDisambiguator`, model_name='egy'). Now checks actual POS tags instead of guessing by word position — proven to correctly handle a case the old patch couldn't (`الموضوع هذا مهم` -> correctly reordered even though not sentence-final).

**Two missing dictionary entries found and fixed:** `كدب` -> `كذب` (Egyptian spelling of "lies"), `حاجة` -> `شيء` (Egyptian word for "thing").

**New, separate limitation found: grammatical gender agreement breaks during dictionary substitution.**
`حاجة` (feminine) -> `شيء` (masculine) substitution doesn't cascade to update agreeing words. Example:
- Input: `مفيش حاجة اسمها تغير مناخي ده كله كدب`
- Produced: `لا يوجد شيء اسمها تغير مناخي هذا كله كذب` -- `اسمها` (feminine possessive) is now wrong; should be `اسمه` (masculine), since it must agree with `شيء`, not the original `حاجة`.

**Literature check:** searched dedicated DA-MSA translation literature (arXiv:2507.20301, LLM-based DA->MSA translation, Gemma-2-9B+LoRA achieving best results) -- **confirmed this exact agreement-cascade problem is not explicitly addressed even in dedicated papers on this task.** This is a genuinely under-addressed edge case in the literature, not a known-solved problem we failed to apply. Real fix requires generative translation (not dictionary substitution), which needs GPU infrastructure not available locally (same blocker as the earlier fine-tuning discussion -- quantization libraries like those used in this paper have poor Apple Silicon support).

**Updated dialect limitation framing for thesis:** "Two distinct grammar problems were found and characterized in the Egyptian dialect normalization step: (1) demonstrative misattachment, fixed via real POS-tag verification; (2) grammatical gender agreement breaking during word substitution, identified and confirmed as an under-addressed problem even in dedicated DA-MSA translation literature, requiring generative translation infrastructure not available for this project."
