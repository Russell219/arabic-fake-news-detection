"""
clean_fulltext.py
-----------------
Cleans the full_text column in Bucket_B_Truth_CLEAN_FINAL.csv.

Noise patterns found per source:
  Youm7   : "الرئيسية [nav] [date] واتساب كتب [author]" prefix
  RT      : title + " - RT Arabic" repeated, related-article headlines
  AlJazeera: "حفظشارِكْwhatsapp-strokecopylink", "Published On DD/MM/YYYY"
  CNN     : topic-tag footer "أمريكا إسرائيل إيران ..."
  BBC     : date prefix "15 أبريل/ نيسان 2026 [title]"

Strategy
--------
1. Inline removals  – strip known junk substrings / patterns
2. Sentence filter  – split on Arabic sentence boundaries, keep sentences ≥ MIN_SENT_LEN chars
3. Fallback         – if cleaned text < MIN_FINAL_LEN chars, use summary instead
"""

import re
import pandas as pd
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
INPUT_CSV   = "kb_articles_v2.csv"
OUTPUT_CSV  = "kb_articles_v2_clean.csv"
MIN_SENT_LEN  = 40     # minimum chars for a sentence chunk to keep
MIN_FINAL_LEN = 80     # if cleaned text shorter than this, fall back to summary

# ── Noise patterns (order matters — run top-to-bottom) ─────────────────────
# 1) AlJazeera social buttons (no spaces)
INLINE_SUBS = [
    (r'حفظشارِكْwhatsapp-strokecopylink',           ''),
    (r'حفظ\s*شارِكْ\s*whatsapp[^\s]*\s*copylink',  ''),
    # Published On date (AlJazeera)
    (r'Published On\s+[\d/]+',                      ''),
    # Pipe + source name suffix on headline  "عنوان | الجزيرة نت"
    (r'\|\s*(الجزيرة نت|RT Arabic|المصري اليوم|BBC Arabic)[^،.]*', ''),
    # " - RT Arabic" trailing label
    (r'\s*[-–]\s*RT Arabic',                        ''),
    # Arabic date + time stamp  "الثلاثاء، 14 أبريل 2026 06:39 م"
    (r'(السبت|الأحد|الاثنين|الثلاثاء|الأربعاء|الخميس|الجمعة)'
     r'،\s*\d+\s+\w+\s+\d{4}\s+\d+:\d+\s*[صم]',   ''),
    # Short Western date "14-4-2026" or "15/4/2026" (not inside a sentence)
    (r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b',           ''),
    # "صورة أرشيفية"  caption noise
    (r'صورة أرشيفية',                               ''),
    # "واتساب" (WhatsApp share button label)
    (r'\bواتساب\b',                                 ''),
    # "كتب [name]"  byline
    (r'كتب\s+[؀-ۿ]+(?:\s+[؀-ۿ]+){0,3}', ''),
    # Trailing topic-tag lines: 3+ single Arabic words separated by spaces, end of text
    # e.g. "أمريكا إسرائيل إيران الفاتيكان دونالد ترامب"
    (r'(\s+[؀-ۿ]{2,12}){3,}\s*$',         ''),
    # Collapse multiple spaces / strip
    (r'  +',                                         ' '),
]

# Lines / sentences that begin with these trigger removal of that chunk
REMOVE_LINE_STARTS = [
    'الرئيسية',   # navigation breadcrumb
    'تابعوا',     # "Follow us on..."
    'شارك',       # "Share"
    'اقرأ أيضاً',
    'اقرأ أيضا',
    'المزيد:',
    'ذات صلة',
]

# If a sentence chunk CONTAINS any of these, drop it
REMOVE_LINE_CONTAINS = [
    'whatsapp',
    'فيسبوك تويتر',
    'يوتيوب',
    'قناتنا على',
    'تواصل معنا',
]


def inline_clean(text: str) -> str:
    """Apply regex substitutions to remove known boilerplate."""
    for pattern, repl in INLINE_SUBS:
        text = re.sub(pattern, repl, text, flags=re.UNICODE)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """
    Split Arabic text into sentence-like chunks.
    Boundaries: ". " / ".\n" / "؟ " / "! " / "\n"
    Keep the delimiter with the sentence.
    """
    # Normalize newlines to space first, then split on sentence-ending punctuation
    text = text.replace('\n', ' ').replace('\r', ' ')
    # Split on ". " / "؟ " / "! " but keep delimiter with left side
    chunks = re.split(r'(?<=[.؟!])\s+', text)
    return [c.strip() for c in chunks if c.strip()]


def is_noise_chunk(chunk: str) -> bool:
    """Return True if the chunk should be discarded."""
    # Too short
    if len(chunk) < MIN_SENT_LEN:
        return True
    # Starts with navigation
    for start in REMOVE_LINE_STARTS:
        if chunk.startswith(start):
            return True
    # Contains known noise
    cl = chunk.lower()
    for phrase in REMOVE_LINE_CONTAINS:
        if phrase in cl:
            return True
    return False


def clean_full_text(raw: str, summary: str) -> str:
    """
    Full pipeline: inline subs → sentence filter → fallback to summary.
    Returns cleaned text string.
    """
    if not isinstance(raw, str) or not raw.strip():
        return summary if isinstance(summary, str) else ''

    # Step 1 – inline replacements
    text = inline_clean(raw)

    # Step 2 – sentence-level filter
    sentences = split_sentences(text)
    kept = [s for s in sentences if not is_noise_chunk(s)]
    cleaned = ' '.join(kept).strip()

    # Step 3 – fallback
    if len(cleaned) < MIN_FINAL_LEN:
        return summary if isinstance(summary, str) else cleaned

    return cleaned


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    base = Path(__file__).parent
    df = pd.read_csv(base / INPUT_CSV)
    print(f"Loaded {len(df)} rows")

    before_empty = (df['full_text'].isna() | (df['full_text'] == '')).sum()
    print(f"Empty full_text before cleaning: {before_empty}")

    df['full_text_clean'] = df.apply(
        lambda r: clean_full_text(r['full_text'], r['summary']), axis=1
    )

    after_empty = (df['full_text_clean'] == '').sum()
    print(f"Empty full_text_clean after cleaning: {after_empty}")

    # Measure average length improvement
    avg_before = df['full_text'].fillna('').str.len().mean()
    avg_after  = df['full_text_clean'].str.len().mean()
    print(f"Avg chars before: {avg_before:.0f}  →  after: {avg_after:.0f}")

    # How many fell back to summary?
    used_summary = df.apply(
        lambda r: (
            isinstance(r['summary'], str) and
            r['full_text_clean'] == r['summary']
        ), axis=1
    ).sum()
    print(f"Rows using summary fallback: {used_summary}")

    # Save
    out_path = base / OUTPUT_CSV
    df.to_csv(out_path, index=False)
    print(f"\n✅ Saved: {out_path}")

    # ── Quick visual check ────────────────────────────────────────────────
    print("\n── Sample comparisons ──")
    for src in ['Youm7_Politics', 'RT_Arabic', 'AlJazeera', 'BBC_Arabic', 'CNN_Arabic']:
        rows = df[(df['source'] == src) & (df['full_text_clean'].str.len() > 80)]
        if rows.empty:
            continue
        row = rows.iloc[0]
        print(f"\n[{src}]")
        print(f"  BEFORE ({len(str(row['full_text']))} chars): {str(row['full_text'])[:200]!r}")
        print(f"  AFTER  ({len(row['full_text_clean'])} chars): {row['full_text_clean'][:200]!r}")


if __name__ == '__main__':
    main()
