"""
extract_propositions.py
-----------------------
Way 3 proposition extraction from clean full_text.

Methodology (cites Chen et al. EMNLP 2024 as motivation):
  - Granularity: sentence-level (finer than passage, coarser than full LLM propositions)
  - Context enrichment: sentences starting with connectors/pronouns get
    the article title prepended → makes each chunk self-contained
  - This approximates atomic propositions without requiring an LLM

Output: df_propositions_clean.csv
  Columns: proposition, title, article_id, source
"""

import re
import pandas as pd
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
INPUT_CSV  = "Bucket_B_Truth_CLEAN_FINAL_v2.csv"
OUTPUT_CSV = "df_propositions_clean.csv"
MIN_LEN    = 40   # minimum chars for a proposition to be kept

# Arabic connectors / pronouns that signal the sentence needs context
CONTEXT_NEEDED = {
    # Conjunctions
    "وقد", "وكان", "وكانت", "وأن", "وإن", "وفي", "وعلى", "وهو", "وهي",
    "وهم", "وأشار", "وأضاف", "وأكد", "وأوضح", "وتابع", "وتشير", "وبين",
    "وذكر", "وأعلن", "وقال", "وأفاد", "ولفت", "ونوه", "وأوضح", "ولاحظ",
    "فأشار", "فأكد", "فقال", "فأضاف", "فأوضح",
    # Demonstratives at start
    "هذا", "هذه", "هذان", "هؤلاء", "ذلك", "تلك", "أولئك",
    # Pronouns at start
    "هو", "هي", "هم", "هن", "هما",
    # "as for" constructions
    "أما", "بينما", "كما",
}

# Sentence-ending punctuation we split on
SENT_SPLIT = re.compile(r'(?<=[.؟!])\s+')


def split_into_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries, return stripped non-empty chunks."""
    text = text.replace('\n', ' ').replace('\r', ' ')
    chunks = SENT_SPLIT.split(text)
    return [c.strip() for c in chunks if c.strip()]


def needs_context(sentence: str) -> bool:
    """Return True if the sentence starts with a connector or pronoun."""
    first_word = sentence.split()[0] if sentence.split() else ''
    return first_word in CONTEXT_NEEDED


def make_proposition(sentence: str, title: str) -> str:
    """
    If sentence is self-contained, return as-is.
    Otherwise prepend title context: "[title]: sentence"
    """
    if needs_context(sentence) and title and title != 'nan':
        return f"{title.strip()}: {sentence}"
    return sentence


def extract_propositions(df: pd.DataFrame) -> pd.DataFrame:
    """Process all articles and return flat DataFrame of propositions."""
    rows = []
    for idx, row in df.iterrows():
        text   = str(row.get('full_text_clean', ''))
        title  = str(row.get('title', ''))
        source = str(row.get('source', ''))

        if not text.strip():
            continue

        sentences = split_into_sentences(text)
        for sent in sentences:
            if len(sent) < MIN_LEN:
                continue
            prop = make_proposition(sent, title)
            rows.append({
                'proposition': prop,
                'title':       title,
                'article_id':  idx,
                'source':      source,
            })

    return pd.DataFrame(rows)


def main():
    base = Path(__file__).parent
    df   = pd.read_csv(base / INPUT_CSV)
    print(f"Loaded {len(df)} articles")
    print(f"Sources: {df['source'].value_counts().to_dict()}")

    df_props = extract_propositions(df)
    print(f"\nTotal propositions extracted: {len(df_props)}")

    # Dedup
    before = len(df_props)
    df_props = df_props.drop_duplicates(subset='proposition').reset_index(drop=True)
    print(f"After dedup: {len(df_props)}  (removed {before - len(df_props)} duplicates)")

    # Stats
    context_added = df_props['proposition'].str.contains(': ').sum()
    print(f"Context-enriched propositions: {context_added} ({100*context_added/len(df_props):.1f}%)")
    print(f"Avg proposition length: {df_props['proposition'].str.len().mean():.0f} chars")

    # Save
    out = base / OUTPUT_CSV
    df_props.to_csv(out, index=False)
    print(f"\n✅ Saved: {out}")

    # Quick sample
    print("\n── Sample propositions ──")
    for i, row in df_props.sample(5, random_state=42).iterrows():
        print(f"  [{row['source']}] {row['proposition'][:100]}")


if __name__ == '__main__':
    main()
