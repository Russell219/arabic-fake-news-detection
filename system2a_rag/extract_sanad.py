"""
extract_sanad.py
----------------
Samples Arabic news articles from the SANAD HuggingFace dataset
(arbml/SANAD, 141k articles) and outputs a CSV compatible with
clean_fulltext.py → extract_propositions.py pipeline.

SANAD label mapping (empirically verified):
  0 → Technology / IT
  1 → Local Politics / Society
  2 → Media / Communications
  3 → Religion / فقه
  4 → Health / Medical
  5 → Culture / Arts
  6 → Sports

Strategy:
  - Skip label 6 (sports) — least useful for fact-checking
  - Sample evenly from the other 6 categories
  - Filter: article length ≥ MIN_LEN chars
  - Derive title: first sentence (up to first "." or 80 chars)
  - summary: first two sentences joined
"""

import re
import random
import pandas as pd
from pathlib import Path
from datasets import load_dataset

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_CSV   = "kb_articles_sanad.csv"
SAMPLES_PER_LABEL = 150   # 150 × 6 labels = 900 articles
MIN_LEN      = 300        # skip very short articles
RANDOM_SEED  = 42

LABEL_NAMES = {
    0: "SANAD_Tech",
    1: "SANAD_Politics",
    2: "SANAD_Media",
    3: "SANAD_Religion",
    4: "SANAD_Health",
    5: "SANAD_Culture",
    # 6 = Sports — skipped
}

USEFUL_LABELS = set(LABEL_NAMES.keys())  # 0–5


def derive_title(text: str) -> str:
    """Extract first sentence as title (up to 100 chars)."""
    # Split on first period, question mark, or exclamation
    m = re.search(r'[.؟!]', text)
    if m and m.start() > 10:
        title = text[:m.start()].strip()
    else:
        title = text[:80].strip()
    # Remove leading byline patterns like "نورالدين ثلاج-أخبارنا:"
    title = re.sub(r'^[^:]{0,30}:', '', title).strip()
    return title[:120]  # cap length


def derive_summary(text: str) -> str:
    """First two sentences as summary."""
    parts = re.split(r'(?<=[.؟!])\s+', text, maxsplit=3)
    return ' '.join(parts[:2]).strip()[:400]


def main():
    random.seed(RANDOM_SEED)
    base = Path(__file__).parent

    print("Loading SANAD dataset (141k articles)...")
    ds = load_dataset('arbml/SANAD', split='train')
    print(f"Loaded {len(ds)} articles")

    # Group indices by label
    from collections import defaultdict
    label_indices = defaultdict(list)
    for i, item in enumerate(ds):
        if item['label'] in USEFUL_LABELS:
            if len(item['Article']) >= MIN_LEN:
                label_indices[item['label']].append(i)

    print("\nUsable articles per label:")
    for label, indices in sorted(label_indices.items()):
        print(f"  {LABEL_NAMES[label]}: {len(indices)}")

    # Sample from each label
    rows = []
    for label, indices in sorted(label_indices.items()):
        sampled = random.sample(indices, min(SAMPLES_PER_LABEL, len(indices)))
        for idx in sampled:
            article = ds[idx]['Article']
            rows.append({
                'source':     LABEL_NAMES[label],
                'title':      derive_title(article),
                'summary':    derive_summary(article),
                'link':       '',
                'timestamp':  '',
                'full_text':  article,
            })

    df = pd.DataFrame(rows)
    print(f"\nTotal sampled: {len(df)} articles")
    print("Source distribution:", df['source'].value_counts().to_dict())

    out = base / OUTPUT_CSV
    df.to_csv(out, index=False)
    print(f"\n✅ Saved: {out}")

    # Quick preview
    print("\n── Samples ──")
    for src in df['source'].unique()[:3]:
        row = df[df['source'] == src].iloc[0]
        print(f"\n[{src}]")
        print(f"  Title: {row['title'][:80]}")
        print(f"  Text:  {row['full_text'][:150]!r}")


if __name__ == '__main__':
    main()
