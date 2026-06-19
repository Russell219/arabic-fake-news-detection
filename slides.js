const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "System 2A — RAG Fact-Verification Engine";

const BG       = "0D1117";   // near-black
const NAVY     = "161B22";   // card bg
const BLUE     = "3B82F6";   // accent blue
const LBLUE    = "93C5FD";   // light blue
const GREEN    = "22C55E";
const YELLOW   = "FACC15";
const PURPLE   = "A78BFA";
const WHITE    = "F0F6FC";
const GRAY     = "8B949E";
const TEAL     = "2DD4BF";

// ── SLIDE 1: Title ─────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  // Left accent bar
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.06, h: 5.625, fill: { color: BLUE } });

  // Eyebrow
  s.addText("GRADUATION PROJECT · SYSTEM 2A", {
    x: 0.4, y: 1.2, w: 9, h: 0.4,
    fontSize: 11, color: BLUE, bold: true, charSpacing: 4, align: "left"
  });

  // Main title
  s.addText("RAG Fact-Verification Engine", {
    x: 0.4, y: 1.7, w: 9, h: 1.2,
    fontSize: 40, color: WHITE, bold: true, align: "left"
  });

  // Subtitle
  s.addText("A Hybrid AI Framework for Arabic Fake News Detection", {
    x: 0.4, y: 2.85, w: 8.5, h: 0.5,
    fontSize: 16, color: LBLUE, align: "left"
  });

  // Divider line
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 3.45, w: 4, h: 0.04, fill: { color: GRAY } });

  // Author / supervisor / date
  s.addText([
    { text: "Russell Tamer", options: { bold: true, color: WHITE } },
    { text: "  ·  Supervised by Dr. Cherry  ·  June 2026", options: { color: GRAY } }
  ], { x: 0.4, y: 3.6, w: 9, h: 0.4, fontSize: 13 });

  // Tech tags
  const tags = ["E5-large", "RRF Fusion", "ChromaDB", "Cross-Encoder", "Arabic NLP"];
  tags.forEach((t, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.4 + i * 1.85, y: 4.4, w: 1.7, h: 0.35,
      fill: { color: "1E3A5F" }, rectRadius: 0.05
    });
    s.addText(t, {
      x: 0.4 + i * 1.85, y: 4.4, w: 1.7, h: 0.35,
      fontSize: 10, color: LBLUE, align: "center", valign: "middle"
    });
  });
}

// ── SLIDE 2: Architecture ──────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("System Architecture — Dual-Bucket Cascade", {
    x: 0.4, y: 0.2, w: 9.2, h: 0.5,
    fontSize: 22, color: WHITE, bold: true, align: "left"
  });

  // Helper to draw a stage box
  const box = (x, y, w, h, label, sub, col) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: "161B22" }, line: { color: col, width: 1.5 } });
    s.addText(label, { x, y: y + 0.05, w, h: 0.28, fontSize: 11, color: col, bold: true, align: "center" });
    if (sub) s.addText(sub, { x, y: y + 0.32, w, h: 0.22, fontSize: 8.5, color: GRAY, align: "center" });
  };

  const arr = (x1, y1, x2, y2, col) => {
    s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: col, width: 1.5 } });
  };

  // Stage 1: Input
  box(3.7, 0.82, 2.6, 0.62, "Arabic Claim Input", "MSA or Egyptian Dialect", BLUE);

  // Arrow down
  arr(5.0, 1.44, 5.0, 1.65, GRAY);

  // Stage 1: Dialect
  box(3.2, 1.65, 3.6, 0.62, "Stage 1 — Dialect Detection", "CAMeL Classifier · EGY→MSA Normalization", LBLUE);

  arr(5.0, 2.27, 5.0, 2.48, GRAY);

  // Stage 2: Bucket A
  box(1.2, 2.48, 7.6, 1.0, "Stage 2 — Bucket A: Verified Claims DB", "21,001 claims · AraFacts + Saheeh Masr · E5-large cosine · HIGH ≥ 0.86 · POSSIBLE ≥ 0.84", BLUE);

  // Bucket A early exit arrow (right)
  arr(8.8, 2.98, 9.4, 2.98, GREEN);
  s.addText("✓ Early Exit", { x: 8.82, y: 2.72, w: 1.0, h: 0.22, fontSize: 8, color: GREEN, align: "left" });
  s.addText("TRUE / FALSE", { x: 8.82, y: 3.0, w: 1.0, h: 0.22, fontSize: 8, color: GREEN, align: "left" });

  // Bucket A fallthrough arrow (down)
  arr(5.0, 3.48, 5.0, 3.68, PURPLE);
  s.addText("score < 0.84", { x: 5.05, y: 3.5, w: 1.2, h: 0.2, fontSize: 8, color: PURPLE });

  // Stage 3: Bucket B
  box(1.2, 3.68, 7.6, 1.0, "Stage 3 — Bucket B: News Knowledge Base", "20,687 propositions · RRF (E5+BM25) · NER boosting · Cross-Encoder rerank → top-5", PURPLE);

  // Arrow down
  arr(5.0, 4.68, 5.0, 4.88, GRAY);

  // Output
  box(2.8, 4.88, 4.4, 0.55, "JSON Output → Youssef (System 2B)", "verdict · confidence · bucket_a[] · bucket_b[]", TEAL);
}

// ── SLIDE 3: Papers ────────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("Papers Implemented", {
    x: 0.4, y: 0.2, w: 9.2, h: 0.5,
    fontSize: 22, color: WHITE, bold: true, align: "left"
  });
  s.addText("What I took from each paper and applied to System 2A", {
    x: 0.4, y: 0.65, w: 9.2, h: 0.3,
    fontSize: 13, color: GRAY, align: "left"
  });

  const papers = [
    {
      num: "01",
      title: "ARAG — Agent-Based Hybrid\nSemantic-Lexical RAG",
      took: ["NER entity boosting (+0.005 per matched entity)", "Cross-encoder reranker (top-20 → top-5)", "RRF fusion as replacement for weighted sum"],
      col: BLUE
    },
    {
      num: "02",
      title: "Exploring RAG in Arabic\n(2024)",
      took: ["E5-large as retrieval encoder", "\"query: \" / \"passage: \" prefix strategy", "Mean pooling + L2 normalize over CLS token"],
      col: TEAL
    },
    {
      num: "03",
      title: "Multilingual Fact-Checked\nClaim Retrieval",
      took: ["ISRI stemmer for Arabic BM25 tokenization", "Proposition-level retrieval rationale", "Cross-lingual evaluation methodology"],
      col: YELLOW
    },
    {
      num: "04",
      title: "Hybrid RAG for Islamic\nQA in Arabic",
      took: ["BM25 calibration: k1=1.2, b=0.75", "RRF formula: 1/(60+rank)", "Hybrid outperforms dense-only on Arabic"],
      col: PURPLE
    }
  ];

  const positions = [
    { x: 0.25, y: 1.05 },
    { x: 5.05, y: 1.05 },
    { x: 0.25, y: 3.1 },
    { x: 5.05, y: 3.1 }
  ];

  papers.forEach((p, i) => {
    const { x, y } = positions[i];
    const W = 4.5, H = 1.85;

    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: W, h: H,
      fill: { color: "161B22" },
      line: { color: p.col, width: 1 }
    });

    // Number badge
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.42, h: H, fill: { color: p.col } });
    s.addText(p.num, { x, y: y + H/2 - 0.2, w: 0.42, h: 0.4, fontSize: 13, color: "0D1117", bold: true, align: "center" });

    // Title
    s.addText(p.title, {
      x: x + 0.5, y: y + 0.1, w: W - 0.6, h: 0.5,
      fontSize: 11, color: WHITE, bold: true, align: "left"
    });

    // Bullets
    const bulletItems = p.took.map((t, bi) => ({
      text: t,
      options: { bullet: true, color: GRAY, fontSize: 9.5, breakLine: bi < p.took.length - 1 }
    }));
    s.addText(bulletItems, {
      x: x + 0.5, y: y + 0.6, w: W - 0.62, h: 1.1, valign: "top"
    });
  });
}

// ── SLIDE 4: Evaluation ────────────────────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("Evaluation Results", {
    x: 0.4, y: 0.2, w: 9.2, h: 0.5,
    fontSize: 22, color: WHITE, bold: true, align: "left"
  });
  s.addText("Same 200 AraFacts test pairs · K=5 · EVAL_SEED=42", {
    x: 0.4, y: 0.65, w: 9, h: 0.3,
    fontSize: 12, color: GRAY, align: "left"
  });

  // Table
  const tData = [
    [
      { text: "System", options: { bold: true, color: WHITE, fill: { color: "1E3A5F" } } },
      { text: "P@1",    options: { bold: true, color: WHITE, fill: { color: "1E3A5F" }, align: "center" } },
      { text: "R@3",    options: { bold: true, color: WHITE, fill: { color: "1E3A5F" }, align: "center" } },
      { text: "MRR",    options: { bold: true, color: WHITE, fill: { color: "1E3A5F" }, align: "center" } },
    ],
    [
      { text: "v1 — BM25 only",          options: { color: GRAY } },
      { text: "0.880", options: { color: GRAY, align: "center" } },
      { text: "0.920", options: { color: GRAY, align: "center" } },
      { text: "0.899", options: { color: GRAY, align: "center" } },
    ],
    [
      { text: "v1 — AraBERT only",        options: { color: GRAY } },
      { text: "0.415", options: { color: GRAY, align: "center" } },
      { text: "0.630", options: { color: GRAY, align: "center" } },
      { text: "0.527", options: { color: GRAY, align: "center" } },
    ],
    [
      { text: "v1 — Hybrid (AraBERT + α=0.65)", options: { color: GRAY } },
      { text: "0.885", options: { color: GRAY, align: "center" } },
      { text: "0.930", options: { color: GRAY, align: "center" } },
      { text: "0.909", options: { color: GRAY, align: "center" } },
    ],
    [
      { text: "v2 — BM25 only",           options: { color: LBLUE } },
      { text: "0.910", options: { color: LBLUE, align: "center" } },
      { text: "0.940", options: { color: LBLUE, align: "center" } },
      { text: "0.929", options: { color: LBLUE, align: "center" } },
    ],
    [
      { text: "v2 — E5-large only",       options: { color: WHITE } },
      { text: "0.965", options: { color: GREEN, bold: true, align: "center" } },
      { text: "0.980", options: { color: GREEN, bold: true, align: "center" } },
      { text: "0.972", options: { color: GREEN, bold: true, align: "center" } },
    ],
    [
      { text: "v2 — RRF Hybrid (ours)",   options: { color: WHITE, bold: true } },
      { text: "0.935", options: { color: GREEN, bold: true, align: "center" } },
      { text: "0.980", options: { color: GREEN, bold: true, align: "center" } },
      { text: "0.958", options: { color: GREEN, bold: true, align: "center" } },
    ],
  ];

  s.addTable(tData, {
    x: 0.4, y: 1.0, w: 5.8,
    colW: [3.2, 0.85, 0.85, 0.9],
    border: { pt: 0.5, color: "30363D" },
    fill: { color: "161B22" },
    fontSize: 11,
    color: WHITE,
    rowH: 0.48
  });

  // Big stat callouts on the right
  const stats = [
    { val: "+150%", label: "E5-large P@1\nvs AraBERT", col: GREEN },
    { val: "+5pts", label: "Hybrid P@1\nv1 → v2", col: BLUE },
    { val: "7 / 2", label: "Cases hybrid\nrecovers vs loses", col: PURPLE },
  ];

  stats.forEach((st, i) => {
    const sx = 6.6, sy = 1.05 + i * 1.45;
    s.addShape(pres.shapes.RECTANGLE, {
      x: sx, y: sy, w: 3.0, h: 1.25,
      fill: { color: "161B22" }, line: { color: st.col, width: 1.5 }
    });
    s.addText(st.val, {
      x: sx, y: sy + 0.1, w: 3.0, h: 0.62,
      fontSize: 34, color: st.col, bold: true, align: "center"
    });
    s.addText(st.label, {
      x: sx, y: sy + 0.72, w: 3.0, h: 0.45,
      fontSize: 10, color: GRAY, align: "center"
    });
  });
}

// ── SLIDE 5: Limitations & Future Work ────────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: BG };

  s.addText("Limitations, Solutions & Future Work", {
    x: 0.4, y: 0.2, w: 9.2, h: 0.5,
    fontSize: 22, color: WHITE, bold: true, align: "left"
  });

  // LEFT: Limitations + Solutions
  s.addText("LIMITATIONS → HOW I SOLVED THEM", {
    x: 0.4, y: 0.78, w: 5.0, h: 0.3,
    fontSize: 10, color: BLUE, bold: true, charSpacing: 2
  });

  const lims = [
    {
      prob: "AraBERT (MLM) weak at retrieval",
      sol:  "→ Switched to E5-large (retrieval-optimized): P@1 0.415 → 0.965",
      col: GREEN
    },
    {
      prob: "Weighted sum needed manual α tuning",
      sol:  "→ RRF fusion: parameter-free, rank-based, robust across queries",
      col: TEAL
    },
    {
      prob: "Thresholds calibrated for AraBERT scores",
      sol:  "→ Re-calibrated for E5 distribution: HIGH ≥ 0.86, POSSIBLE ≥ 0.84",
      col: YELLOW
    },
    {
      prob: "Egyptian dialect queries fail in MSA DB",
      sol:  "→ CAMeL dialect detection + EGY→MSA normalization pipeline",
      col: PURPLE
    },
  ];

  lims.forEach((l, i) => {
    const y = 1.15 + i * 1.03;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.4, y, w: 5.0, h: 0.92,
      fill: { color: "161B22" }, line: { color: l.col, width: 1 }
    });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y, w: 0.05, h: 0.92, fill: { color: l.col } });
    s.addText(l.prob, {
      x: 0.55, y: y + 0.06, w: 4.78, h: 0.3,
      fontSize: 10.5, color: WHITE, bold: true, align: "left"
    });
    s.addText(l.sol, {
      x: 0.55, y: y + 0.38, w: 4.78, h: 0.44,
      fontSize: 9.5, color: GRAY, align: "left"
    });
  });

  // RIGHT: Future Work
  s.addText("FUTURE WORK", {
    x: 5.7, y: 0.78, w: 3.9, h: 0.3,
    fontSize: 10, color: BLUE, bold: true, charSpacing: 2
  });

  const future = [
    { icon: "📝", text: "Paraphrase evaluation\nvia Claude API (50 pairs)" },
    { icon: "🔗", text: "End-to-end integration\nwith Sarah (Sys 1) + Youssef (Sys 2B)" },
    { icon: "🏷️", text: "Human-annotated Bucket B\nrelevance pairs for formal eval" },
    { icon: "🌍", text: "Expand dialect support\nbeyond Egyptian (Levantine, Gulf)" },
  ];

  future.forEach((f, i) => {
    const y = 1.15 + i * 1.03;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 5.7, y, w: 3.9, h: 0.92,
      fill: { color: "161B22" }, line: { color: "30363D", width: 1 }
    });
    s.addText(f.icon, {
      x: 5.75, y: y + 0.18, w: 0.55, h: 0.55,
      fontSize: 22, align: "center", valign: "middle"
    });
    s.addText(f.text, {
      x: 6.35, y: y + 0.1, w: 3.1, h: 0.72,
      fontSize: 10.5, color: WHITE, align: "left", valign: "middle"
    });
  });
}

// ── Save ───────────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "/Users/russelltamer/Desktop/system 2 RAG/system2A_presentation.pptx" })
  .then(() => console.log("✅ Saved: system2A_presentation.pptx"))
  .catch(e => console.error("❌", e));
