const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Arabic Fake News Detection — Team Presentation";

// ── Palette ────────────────────────────────────────────────────────────────
const WHITE  = "FFFFFF";
const OFFWHT = "F7F8FA";
const DARK   = "1A1A2E";
const NAVY   = "1F3A6E";
const BLUE   = "2563EB";
const LBLUE  = "DBEAFE";
const GREEN  = "166534";
const LGREEN = "DCFCE7";
const AMBER  = "92400E";
const LAMBER = "FEF3C7";
const GRAY   = "6B7280";
const LGRAY  = "F3F4F6";
const TEXT   = "111827";

// ── SLIDE 1: Title ─────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: DARK };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: BLUE }, line: { color: BLUE } });

  s.addText("A Hybrid AI Framework for", {
    x: 0.6, y: 1.2, w: 8.8, h: 0.6,
    fontSize: 22, color: "93C5FD", bold: false, align: "center"
  });
  s.addText("Arabic Fake News Detection", {
    x: 0.6, y: 1.75, w: 8.8, h: 0.8,
    fontSize: 36, color: WHITE, bold: true, align: "center"
  });
  s.addText("and Fact Verification", {
    x: 0.6, y: 2.45, w: 8.8, h: 0.6,
    fontSize: 28, color: WHITE, bold: true, align: "center"
  });

  // Team row
  const members = [
    { name: "Sarah", role: "Text Classification" },
    { name: "Russell", role: "RAG Retrieval" },
    { name: "Youssef", role: "Verdict Engine" }
  ];
  const xs = [1.0, 3.9, 6.8];
  members.forEach((m, i) => {
    s.addShape(pres.shapes.RECTANGLE, { x: xs[i], y: 3.5, w: 2.2, h: 1.2, fill: { color: "1E3A6E" }, line: { color: "3B82F6" }, rectRadius: 0.08 });
    s.addText(m.name, { x: xs[i], y: 3.62, w: 2.2, h: 0.42, fontSize: 16, bold: true, color: WHITE, align: "center" });
    s.addText(m.role, { x: xs[i], y: 4.04, w: 2.2, h: 0.36, fontSize: 10, color: "93C5FD", align: "center" });
  });

  s.addText("Supervisor: Dr. Cherry  ·  June 2026", {
    x: 0.6, y: 5.0, w: 8.8, h: 0.35,
    fontSize: 11, color: GRAY, align: "center"
  });
}

// ── SLIDE 2: System Overview ───────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: OFFWHT };

  s.addText("System Overview", {
    x: 0.5, y: 0.18, w: 9, h: 0.5,
    fontSize: 26, bold: true, color: TEXT, align: "left"
  });
  s.addText("Sequential three-system pipeline — Arabic claim → classification → retrieval → verdict", {
    x: 0.5, y: 0.65, w: 9, h: 0.28,
    fontSize: 11, color: GRAY, align: "left"
  });

  // Pipeline PNG
  s.addImage({ path: "/Users/russelltamer/Desktop/system 2 RAG/full_system_pipeline.png", x: 1.8, y: 0.95, w: 6.4, h: 4.6 });
}

// ── SLIDE 3: Sarah ────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 5.625, fill: { color: "166534" }, line: { color: "166534" } });

  s.addText("System 1 — Sarah", {
    x: 0.4, y: 0.25, w: 9.2, h: 0.55,
    fontSize: 28, bold: true, color: TEXT
  });
  s.addText("Text Classification", {
    x: 0.4, y: 0.78, w: 9.2, h: 0.3,
    fontSize: 14, color: "166534", bold: true
  });

  // Left column
  const cards = [
    { title: "Model", body: "MARBERt fine-tuned on Arabic fake news dataset", color: LGREEN, tc: GREEN },
    { title: "Comparison", body: "Transformer vs CNN vs SVM — evaluates multiple approaches", color: LGREEN, tc: GREEN },
    { title: "Dialect Support", body: "Handles both MSA and Egyptian Arabic input", color: LGREEN, tc: GREEN },
  ];
  cards.forEach((c, i) => {
    const cy = 1.3 + i * 1.1;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: cy, w: 4.4, h: 0.95, fill: { color: c.color }, line: { color: "BBF7D0" }, rectRadius: 0.07 });
    s.addText(c.title, { x: 0.55, y: cy + 0.08, w: 4.1, h: 0.28, fontSize: 11, bold: true, color: c.tc });
    s.addText(c.body, { x: 0.55, y: cy + 0.36, w: 4.1, h: 0.46, fontSize: 10, color: TEXT });
  });

  // Right column — outputs
  s.addText("Output Signals", { x: 5.2, y: 1.25, w: 4.4, h: 0.32, fontSize: 13, bold: true, color: TEXT });

  const outputs = [
    { label: "FAKE_LIKELY", desc: "High suspicion → sent to Russell for verification", color: "FEE2E2", tc: "991B1B" },
    { label: "UNCERTAIN", desc: "Borderline → Russell retrieves evidence", color: "FEF3C7", tc: "92400E" },
    { label: "REAL_LIKELY", desc: "Looks true → still verified by Russell", color: "DCFCE7", tc: "166534" },
  ];
  outputs.forEach((o, i) => {
    const oy = 1.65 + i * 1.1;
    s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: oy, w: 4.4, h: 0.9, fill: { color: o.color }, line: { color: o.color }, rectRadius: 0.07 });
    s.addText(o.label, { x: 5.35, y: oy + 0.08, w: 4.1, h: 0.28, fontSize: 11, bold: true, color: o.tc });
    s.addText(o.desc, { x: 5.35, y: oy + 0.36, w: 4.1, h: 0.42, fontSize: 10, color: TEXT });
  });

  s.addText("All three outputs → forwarded to Russell with confidence score", {
    x: 0.4, y: 4.9, w: 9.2, h: 0.3,
    fontSize: 10, color: GRAY, italic: true
  });
}

// ── SLIDE 4: Russell ──────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 5.625, fill: { color: BLUE }, line: { color: BLUE } });

  s.addText("System 2A — Russell", {
    x: 0.4, y: 0.25, w: 9.2, h: 0.55,
    fontSize: 28, bold: true, color: TEXT
  });
  s.addText("RAG Fact-Verification Engine", {
    x: 0.4, y: 0.78, w: 9.2, h: 0.3,
    fontSize: 14, color: BLUE, bold: true
  });

  // Bucket A
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 1.2, w: 4.4, h: 2.2, fill: { color: LBLUE }, line: { color: "93C5FD" }, rectRadius: 0.08 });
  s.addText("Bucket A — Verified Claims", { x: 0.55, y: 1.28, w: 4.1, h: 0.32, fontSize: 12, bold: true, color: NAVY });
  s.addText("21,001 claims · AraFacts + Saheeh Masr", { x: 0.55, y: 1.58, w: 4.1, h: 0.25, fontSize: 9, color: GRAY });
  s.addText("E5-large multilingual embeddings", { x: 0.55, y: 1.82, w: 4.1, h: 0.25, fontSize: 9, color: TEXT });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.55, y: 2.1, w: 1.8, h: 0.45, fill: { color: LGREEN }, line: { color: "86EFAC" }, rectRadius: 0.05 });
  s.addText("HIGH ≥ 0.86\nDirect verdict", { x: 0.55, y: 2.12, w: 1.8, h: 0.41, fontSize: 8, bold: true, color: GREEN, align: "center" });
  s.addShape(pres.shapes.RECTANGLE, { x: 2.5, y: 2.1, w: 2.1, h: 0.45, fill: { color: LAMBER }, line: { color: "FCD34D" }, rectRadius: 0.05 });
  s.addText("POSSIBLE ≥ 0.84\n→ Youssef NLI", { x: 2.5, y: 2.12, w: 2.1, h: 0.41, fontSize: 8, bold: true, color: AMBER, align: "center" });
  s.addText("Egyptian dialect normalization via CAMeL", { x: 0.55, y: 2.65, w: 4.1, h: 0.25, fontSize: 9, color: GRAY, italic: true });
  s.addText("Score < 0.84 → escalate to Bucket B", { x: 0.55, y: 2.9, w: 4.1, h: 0.25, fontSize: 9, color: GRAY, italic: true });

  // Bucket B
  s.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 1.2, w: 4.4, h: 2.2, fill: { color: "EDE9FE" }, line: { color: "C4B5FD" }, rectRadius: 0.08 });
  s.addText("Bucket B — News Knowledge Base", { x: 5.35, y: 1.28, w: 4.1, h: 0.32, fontSize: 12, bold: true, color: "5B21B6" });
  s.addText("20,687 propositions · 25 Arabic sources", { x: 5.35, y: 1.58, w: 4.1, h: 0.25, fontSize: 9, color: GRAY });

  const bsteps = ["RRF hybrid: BM25 + E5-large fusion", "NER entity boosting", "Cross-encoder reranker (top-20 → top-5)"];
  bsteps.forEach((t, i) => {
    s.addText([{ text: `${i+1}. ${t}`, options: {} }], { x: 5.35, y: 1.82 + i * 0.28, w: 4.1, h: 0.26, fontSize: 9, color: TEXT });
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.35, y: 2.68, w: 4.1, h: 0.45, fill: { color: "F3F4F6" }, line: { color: "E5E7EB" }, rectRadius: 0.05 });
  s.addText("EVIDENCE_FOUND → Youssef NLI\nLOW_CONFIDENCE → UNVERIFIED", { x: 5.35, y: 2.7, w: 4.1, h: 0.41, fontSize: 8, color: TEXT, align: "center" });

  // Papers row
  s.addText("Papers Implemented", { x: 0.4, y: 3.55, w: 9.2, h: 0.3, fontSize: 12, bold: true, color: TEXT });
  const papers = ["ARAG\nRRF + NER boosting", "E5-large\nMultilingual embeddings", "BM25 + ISRI\nArabic stemming", "Cross-Encoder\nReranking"];
  papers.forEach((p, i) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.4 + i * 2.4, y: 3.88, w: 2.2, h: 0.7, fill: { color: LGRAY }, line: { color: "E5E7EB" }, rectRadius: 0.06 });
    s.addText(p, { x: 0.4 + i * 2.4, y: 3.9, w: 2.2, h: 0.66, fontSize: 8.5, color: TEXT, align: "center", valign: "middle" });
  });
}

// ── SLIDE 5: Evaluation ───────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 5.625, fill: { color: BLUE }, line: { color: BLUE } });

  s.addText("Evaluation Results — System 2A", {
    x: 0.4, y: 0.25, w: 9.2, h: 0.55,
    fontSize: 28, bold: true, color: TEXT
  });
  s.addText("200 AraFacts pairs · K=5", {
    x: 0.4, y: 0.78, w: 9.2, h: 0.3,
    fontSize: 13, color: GRAY
  });

  // v1 vs v2 table
  s.addText("Bucket A Retrieval — v1 vs v2", { x: 0.4, y: 1.15, w: 5.5, h: 0.3, fontSize: 12, bold: true, color: TEXT });

  const tRows = [
    ["System", "P@1", "R@3", "MRR", true],
    ["BM25 only (v1)", "0.880", "0.920", "0.899", false],
    ["AraBERT only (v1)", "0.415", "0.630", "0.527", false],
    ["Hybrid v1", "0.885", "0.930", "0.909", false],
    ["BM25 only (v2)", "0.910", "0.940", "0.929", false],
    ["E5-large only", "0.965", "0.980", "0.972", false],
    ["RRF Hybrid v2", "0.935", "0.980", "0.958", false],
  ];
  const cols = [2.4, 0.9, 0.9, 0.9];
  const xs2 = [0.4, 2.85, 3.78, 4.71];

  tRows.forEach((row, ri) => {
    const ry = 1.5 + ri * 0.38;
    const isHeader = row[4];
    const isBest = row[0] === "E5-large only";
    const bg = isHeader ? NAVY : isBest ? LGREEN : (ri % 2 === 0 ? LGRAY : WHITE);
    const tc2 = isHeader ? WHITE : isBest ? GREEN : TEXT;

    row.slice(0, 4).forEach((cell, ci) => {
      s.addShape(pres.shapes.RECTANGLE, { x: xs2[ci], y: ry, w: cols[ci], h: 0.35, fill: { color: bg }, line: { color: "E5E7EB" } });
      s.addText(String(cell), { x: xs2[ci] + 0.05, y: ry + 0.04, w: cols[ci] - 0.1, h: 0.27, fontSize: ci === 0 ? 8.5 : 9, bold: isHeader || (isBest && ci > 0), color: tc2, align: ci === 0 ? "left" : "center" });
    });
  });

  // Why E5-large beats hybrid explanation box
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 4.2, w: 5.5, h: 0.72, fill: { color: LGREEN }, line: { color: "86EFAC" }, rectRadius: 0.05 });
  s.addText("Why E5-large alone > Hybrid on AraFacts:", { x: 0.5, y: 4.23, w: 5.3, h: 0.24, fontSize: 8.5, bold: true, color: GREEN });
  s.addText("AraFacts is MSA-dominant — BM25 already scores 0.910, so RRF fusion adds slight noise (0.965 → 0.935). On dialectal or paraphrased input, hybrid wins: see dialect 0.980 above.", {
    x: 0.5, y: 4.47, w: 5.3, h: 0.42,
    fontSize: 7.5, color: TEXT
  });

  // Paraphrase table
  s.addText("Paraphrase Robustness (Bucket A)", { x: 6.0, y: 1.15, w: 3.7, h: 0.3, fontSize: 12, bold: true, color: TEXT });

  const pRows = [
    ["Level", "P@1", true],
    ["Light rewording", "1.000", false],
    ["Medium rewrite", "0.960", false],
    ["Heavy rewrite", "0.920", false],
    ["Egyptian Dialect", "0.980", false],
  ];
  pRows.forEach((row, ri) => {
    const ry = 1.5 + ri * 0.38;
    const isH = row[2];
    const bg = isH ? NAVY : ri % 2 === 0 ? LGRAY : WHITE;
    const tc2 = isH ? WHITE : TEXT;
    [6.0, 8.8].forEach((px, ci) => {
      const w2 = ci === 0 ? 2.7 : 0.9;
      s.addShape(pres.shapes.RECTANGLE, { x: px, y: ry, w: w2, h: 0.35, fill: { color: bg }, line: { color: "E5E7EB" } });
      s.addText(String(row[ci]), { x: px + 0.05, y: ry + 0.04, w: w2 - 0.1, h: 0.27, fontSize: ci === 0 ? 8.5 : 9, bold: isH, color: tc2, align: ci === 0 ? "left" : "center" });
    });
  });

  s.addText("★ Dialect robustness 0.98 — CAMeL normalization + E5 multilingual encoding", {
    x: 6.0, y: 4.22, w: 3.7, h: 0.3,
    fontSize: 8, color: GREEN, italic: true
  });

  // Bucket B note
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 5.05, w: 9.2, h: 0.42, fill: { color: LGRAY }, line: { color: "E5E7EB" }, rectRadius: 0.06 });
  s.addText("Bucket B (News KB): P@1 = 0.20 on AraFacts · Expected — viral social media rumors don't appear in news sources by design", {
    x: 0.55, y: 5.12, w: 9.0, h: 0.28,
    fontSize: 9, color: GRAY
  });
}

// ── SLIDE 6: Youssef ──────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 5.625, fill: { color: AMBER }, line: { color: AMBER } });

  s.addText("System 2B — Youssef", {
    x: 0.4, y: 0.18, w: 9.2, h: 0.5,
    fontSize: 26, bold: true, color: TEXT
  });
  s.addText("Verdict Engine · NLI + Aggregation Pipeline", {
    x: 0.4, y: 0.66, w: 9.2, h: 0.28,
    fontSize: 13, color: AMBER, bold: true
  });

  // INPUT section
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 1.0, w: 9.2, h: 0.52, fill: { color: LAMBER }, line: { color: "FCD34D" }, rectRadius: 0.07 });
  s.addText("INPUT from Russell:", { x: 0.55, y: 1.04, w: 2.0, h: 0.2, fontSize: 9, bold: true, color: AMBER });
  s.addText("claim  ·  verdict_signal  ·  bucket_a[ ]  ·  bucket_b[ ]", {
    x: 0.55, y: 1.24, w: 9.0, h: 0.2, fontSize: 9, color: TEXT
  });
  s.addText("Model: xlm-roberta-large-xnli", { x: 7.0, y: 1.04, w: 2.5, h: 0.2, fontSize: 8.5, bold: true, color: AMBER, align: "right" });

  // Path 1 — Direct Verdict
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 1.65, w: 4.2, h: 2.05, fill: { color: LGREEN }, line: { color: "86EFAC" }, rectRadius: 0.08 });
  s.addText("Path 1 — Direct Verdict", { x: 0.55, y: 1.72, w: 3.9, h: 0.3, fontSize: 12, bold: true, color: GREEN });
  s.addText("Trigger: HIGH_FAKE_MATCH or HIGH_TRUE_MATCH\n(Bucket A similarity ≥ 0.90)", {
    x: 0.55, y: 2.02, w: 3.9, h: 0.42, fontSize: 8.5, color: TEXT
  });
  s.addText("NLI is NOT run — trust Bucket A directly", { x: 0.55, y: 2.44, w: 3.9, h: 0.22, fontSize: 8.5, color: TEXT });
  s.addText("→ final verdict + confidence score", { x: 0.55, y: 2.66, w: 3.9, h: 0.22, fontSize: 8.5, color: GREEN, bold: true });
  s.addText("Fast path · no NLI computation needed", { x: 0.55, y: 2.9, w: 3.9, h: 0.22, fontSize: 8, color: GRAY, italic: true });
  s.addText("High confidence by design", { x: 0.55, y: 3.12, w: 3.9, h: 0.22, fontSize: 8, color: GRAY, italic: true });

  // Path 2 — NLI + Aggregation
  s.addShape(pres.shapes.RECTANGLE, { x: 4.9, y: 1.65, w: 4.7, h: 2.05, fill: { color: LAMBER }, line: { color: "FCD34D" }, rectRadius: 0.08 });
  s.addText("Path 2 — NLI + Aggregation", { x: 5.05, y: 1.72, w: 4.4, h: 0.3, fontSize: 12, bold: true, color: AMBER });
  s.addText("Trigger: POSSIBLE / EVIDENCE_FOUND / LOW_CONFIDENCE", { x: 5.05, y: 2.02, w: 4.4, h: 0.22, fontSize: 8, color: TEXT });

  const steps2 = [
    "1. Run NLI on each Bucket B proposition",
    "2. Weight stances by hybrid_score (evidence quality)",
    "3. Apply Russell's verdict signal as prior nudge",
    "4. Map ratio → TRUE / FALSE / UNVERIFIED",
    "5. Calculate confidence (capped at 0.95)",
    "6. Build human-readable reason string",
  ];
  steps2.forEach((st, i) => {
    s.addText(st, { x: 5.05, y: 2.26 + i * 0.235, w: 4.4, h: 0.22, fontSize: 8, color: TEXT });
  });

  // OUTPUT row
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 3.82, w: 9.2, h: 0.48, fill: { color: LGRAY }, line: { color: "E5E7EB" }, rectRadius: 0.06 });
  s.addText("OUTPUT:", { x: 0.55, y: 3.9, w: 1.2, h: 0.28, fontSize: 9, bold: true, color: TEXT });
  s.addText("TRUE", { x: 2.0, y: 3.88, w: 1.3, h: 0.32, fontSize: 14, bold: true, color: GREEN, align: "center" });
  s.addText("FALSE", { x: 4.1, y: 3.88, w: 1.3, h: 0.32, fontSize: 14, bold: true, color: "DC2626", align: "center" });
  s.addText("UNVERIFIED", { x: 6.1, y: 3.88, w: 2.2, h: 0.32, fontSize: 14, bold: true, color: AMBER, align: "center" });
  s.addText("+ confidence · stance_breakdown · reason", { x: 8.2, y: 3.9, w: 1.3, h: 0.28, fontSize: 7.5, color: GRAY, align: "center" });

  // File structure
  s.addText("Module breakdown:", { x: 0.4, y: 4.42, w: 2.0, h: 0.25, fontSize: 9, bold: true, color: TEXT });
  const files = [
    { f: "schemas.py", d: "Data models" },
    { f: "nli_model.py", d: "NLI inference" },
    { f: "aggregator.py", d: "Stance weighting" },
    { f: "reason_builder.py", d: "Reason text" },
    { f: "verdict_engine.py", d: "Main orchestrator" },
  ];
  files.forEach((fl, i) => {
    const fx = 0.4 + i * 1.88;
    s.addShape(pres.shapes.RECTANGLE, { x: fx, y: 4.68, w: 1.75, h: 0.6, fill: { color: LGRAY }, line: { color: "E5E7EB" }, rectRadius: 0.05 });
    s.addText(fl.f, { x: fx + 0.05, y: 4.71, w: 1.65, h: 0.26, fontSize: 7.5, bold: true, color: NAVY, align: "center", fontFace: "Courier New" });
    s.addText(fl.d, { x: fx + 0.05, y: 4.97, w: 1.65, h: 0.24, fontSize: 8, color: GRAY, align: "center" });
  });
}

// ── SLIDE 7: Integration ──────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  s.addText("How It All Connects", {
    x: 0.5, y: 0.25, w: 9, h: 0.55,
    fontSize: 28, bold: true, color: TEXT
  });
  s.addText("JSON contract between systems", {
    x: 0.5, y: 0.78, w: 9, h: 0.3,
    fontSize: 13, color: GRAY
  });

  // Flow
  const flow = [
    { sys: "Sarah", color: "166534", bg: LGREEN, msg: "claim + sarah_signal\n+ sarah_confidence" },
    { sys: "Russell", color: NAVY, bg: LBLUE, msg: "verdict_signal + bucket_a[]\n+ bucket_b[] + confidence" },
    { sys: "Youssef", color: AMBER, bg: LAMBER, msg: "final_verdict + confidence\n+ stance_breakdown + reason" },
  ];

  flow.forEach((f, i) => {
    const fx = 0.5 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, { x: fx, y: 1.2, w: 2.7, h: 0.55, fill: { color: f.bg }, line: { color: f.bg }, rectRadius: 0.07 });
    s.addText(f.sys, { x: fx, y: 1.27, w: 2.7, h: 0.4, fontSize: 15, bold: true, color: f.color, align: "center" });
    if (i < 2) {
      s.addShape(pres.shapes.LINE, { x: fx + 2.7, y: 1.47, w: 0.4, h: 0, line: { color: GRAY, width: 1.5 } });
    }
    s.addShape(pres.shapes.RECTANGLE, { x: fx, y: 1.9, w: 2.7, h: 0.8, fill: { color: LGRAY }, line: { color: "E5E7EB" }, rectRadius: 0.06 });
    s.addText("Sends:", { x: fx + 0.1, y: 1.95, w: 2.5, h: 0.22, fontSize: 8, bold: true, color: GRAY });
    s.addText(f.msg, { x: fx + 0.1, y: 2.15, w: 2.5, h: 0.52, fontSize: 8, color: TEXT });
  });

  // JSON example
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.9, w: 9, h: 2.4, fill: { color: "1E1E2E" }, line: { color: "374151" }, rectRadius: 0.08 });
  s.addText("Russell's JSON Output (sample)", { x: 0.7, y: 2.97, w: 8.6, h: 0.28, fontSize: 10, bold: true, color: "93C5FD" });

  const jsonLines = [
    '  "claim": "السيسي باع سيناء لإسرائيل"',
    '  "verdict_signal": "POSSIBLE_FAKE",   "confidence": 0.74',
    '  "bucket_a": [{ "text": "...", "label": "FALSE", "similarity": 0.851 }]',
    '  "bucket_b": [{ "text": "...", "source": "AlJazeera", "score": 0.821 }]',
    '  "sarah_signal": "FAKE_LIKELY",   "sarah_confidence": 0.88',
  ];
  jsonLines.forEach((line, i) => {
    s.addText(line, { x: 0.7, y: 3.28 + i * 0.36, w: 8.8, h: 0.33, fontSize: 8.5, color: "E2E8F0", fontFace: "Courier New" });
  });
}

// ── SLIDE 8: Limitations & Future Work ───────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: DARK };

  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: BLUE }, line: { color: BLUE } });

  s.addText("System 2A — Limitations & How I Will Fix Them", {
    x: 0.5, y: 0.18, w: 9, h: 0.52,
    fontSize: 24, bold: true, color: WHITE
  });

  const items = [
    {
      title: "BM25 Has No Synonym Handling",
      problem: "I use ISRI stemming but no query expansion — if the claim uses a different word than the proposition, BM25 misses the match entirely",
      fix: "Future work: add Arabic synonym expansion (AraVec / CAMeL lexicon) before BM25 tokenization",
      color: "EF4444"
    },
    {
      title: "Cross-Encoder Threshold Not Calibrated",
      problem: "The EVIDENCE_FOUND threshold was not formally calibrated on Arabic fact-checking data — set heuristically, which hurts Bucket B precision",
      fix: "Future work: collect annotated (claim, proposition) pairs → calibrate threshold by F1 on held-out set",
      color: "F59E0B"
    },
    {
      title: "Bucket B Has No Formal Evaluation",
      problem: "No annotated Arabic (claim, proposition) pairs exist for news KB evaluation — manual spot-check only, no reliable P@1 benchmark",
      fix: "Future work: build Arabic claim-proposition annotation dataset; use Saheeh Masr claims + manual relevance labels",
      color: "3B82F6"
    },
    {
      title: "System Is Single-Pass",
      problem: "If Bucket B retrieves nothing useful, the system returns LOW_CONFIDENCE and gives up — ARAG reformulates the query and retries",
      fix: "Future work: implement query reformulation loop — on low top-1 score, expand query and retry up to 2 times",
      color: "8B5CF6"
    },
  ];

  items.forEach((it, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const ix = 0.5 + col * 4.85;
    const iy = 0.9 + row * 2.0;

    s.addShape(pres.shapes.RECTANGLE, { x: ix, y: iy, w: 4.3, h: 1.8, fill: { color: "1E293B" }, line: { color: it.color }, rectRadius: 0.08 });
    s.addShape(pres.shapes.RECTANGLE, { x: ix, y: iy, w: 0.18, h: 1.8, fill: { color: it.color }, line: { color: it.color }, rectRadius: 0.04 });
    s.addText(it.title, { x: ix + 0.28, y: iy + 0.1, w: 3.9, h: 0.3, fontSize: 11, bold: true, color: WHITE });
    s.addText(it.problem, { x: ix + 0.28, y: iy + 0.42, w: 3.9, h: 0.68, fontSize: 8.5, color: "CBD5E1" });
    s.addShape(pres.shapes.RECTANGLE, { x: ix + 0.18, y: iy + 1.13, w: 4.12, h: 0.58, fill: { color: "0F172A" }, line: { color: it.color } });
    s.addText(it.fix, { x: ix + 0.28, y: iy + 1.18, w: 3.9, h: 0.46, fontSize: 8, color: it.color, bold: true });
  });

  s.addText("Thank you  ·  Questions?", {
    x: 0.5, y: 5.1, w: 9, h: 0.3,
    fontSize: 14, color: "93C5FD", align: "center", bold: true
  });
}

// ── Write file ─────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "/Users/russelltamer/Desktop/system 2 RAG/team_presentation.pptx" })
  .then(() => console.log("✅ team_presentation.pptx saved"))
  .catch(e => console.error("Error:", e));
