"""
update_bucket_b.py
------------------
Incremental Bucket B ingestion from live RSS feeds.
Addresses the KB freshness gap identified by VERIFAID (Lopez-Joya et al., 2025)
and motivated by FreshLLMs (Vu et al., 2023).

Designed to run via cron every 4 hours:
  0 */4 * * * cd "/Users/russelltamer/Desktop/system 2 RAG/system2a_rag" && python3 update_bucket_b.py >> update_log.txt 2>&1

Sources selected for domain diversity:
  - BBC Arabic        (international, politics, health, science)
  - CNN Arabic        (tech, science, health, politics)
  - RT Arabic         (general news, sports, politics)
  - DW Arabic         (European affairs, science, culture)
  - Asharq Al-Awsat   (Gulf, economy, politics)
  - Euronews Arabic   (international, science, tech, environment)
  - Sputnik Arabic    (science, health, sports)
"""

import os, re, sys, json, time, logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import chromadb
import feedparser
from newspaper import Article
from transformers import AutoTokenizer, AutoModel
from nltk.stem.isri import ISRIStemmer

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)
log = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE       = "/Users/russelltamer/Desktop/system 2 RAG"
CHROMA_DIR = f"{BASE}/chroma_db"
PROPS_CSV  = f"{BASE}/df_propositions_all.csv"
ARTICLES_CSV = f"{BASE}/Bucket_B_Truth_CLEAN_FINAL.csv"
SEEN_FILE  = f"{BASE}/system2a_rag/seen_articles.json"

# ── RSS Sources ──────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "BBC_Arabic":       "https://feeds.bbci.co.uk/arabic/rss.xml",
    "CNN_Arabic":       "https://arabic.cnn.com/api/v1/rss/rss.xml",
    "RT_Arabic":        "https://arabic.rt.com/rss/",
    "DW_Arabic":        "https://rss.dw.com/xml/rss-ar-all",
    "Asharq_AlAwsat":   "https://aawsat.com/feed",
    "Euronews_Arabic":  "https://arabic.euronews.com/rss",
    "Sputnik_Arabic":   "https://arabic.sputniknews.com/export/rss2/archive/index.xml",
}

# ── Proposition extraction (from extract_propositions.py) ────────────────────
MIN_PROP_LEN = 40
SENT_SPLIT = re.compile(r'(?<=[.؟!])\s+')

CONTEXT_NEEDED = {
    "وقد", "وكان", "وكانت", "وأن", "وإن", "وفي", "وعلى", "وهو", "وهي",
    "وهم", "وأشار", "وأضاف", "وأكد", "وأوضح", "وتابع", "وتشير", "وبين",
    "وذكر", "وأعلن", "وقال", "وأفاد", "ولفت", "ونوه", "وأوضح", "ولاحظ",
    "فأشار", "فأكد", "فقال", "فأضاف", "فأوضح",
    "هذا", "هذه", "هذان", "هؤلاء", "ذلك", "تلك", "أولئك",
    "هو", "هي", "هم", "هن", "هما",
    "أما", "بينما", "كما",
}


def split_into_sentences(text):
    text = text.replace('\n', ' ').replace('\r', ' ')
    chunks = SENT_SPLIT.split(text)
    return [c.strip() for c in chunks if c.strip()]


def make_proposition(sentence, title):
    first_word = sentence.split()[0] if sentence.split() else ''
    if first_word in CONTEXT_NEEDED and title and title != 'nan':
        return f"{title.strip()}: {sentence}"
    return sentence


def extract_propositions_from_article(title, full_text, source):
    rows = []
    sentences = split_into_sentences(full_text)
    for sent in sentences:
        if len(sent) < MIN_PROP_LEN:
            continue
        prop = make_proposition(sent, title)
        rows.append({
            'proposition': prop,
            'title': title,
            'article_id': -1,
            'source': source,
        })
    return rows


# ── E5 Embedding ─────────────────────────────────────────────────────────────
log.info("Loading E5-large model...")
E5_MODEL = "intfloat/multilingual-e5-large"
e5_tokenizer = AutoTokenizer.from_pretrained(E5_MODEL)
e5_model = AutoModel.from_pretrained(E5_MODEL)
e5_model.eval()
log.info("E5-large loaded")


def _mean_pool(token_embeds, attention_mask):
    mask = attention_mask.unsqueeze(-1).expand(token_embeds.size()).float()
    return (token_embeds * mask).sum(1) / mask.sum(1).clamp(min=1e-9)


def get_embeddings_batch(texts, batch_size=16):
    prefixed = [f"passage: {t}" for t in texts]
    all_vecs = []
    for i in range(0, len(prefixed), batch_size):
        batch = prefixed[i:i + batch_size]
        inp = e5_tokenizer(batch, return_tensors="pt", truncation=True,
                           max_length=512, padding=True)
        with torch.no_grad():
            out = e5_model(**inp)
        vecs = _mean_pool(out.last_hidden_state, inp['attention_mask'])
        vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)
        all_vecs.append(vecs.numpy())
    return np.vstack(all_vecs)


# ── Dedup: track what we've already ingested ─────────────────────────────────
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_set), f, ensure_ascii=False)


# ── Fetch articles from RSS ──────────────────────────────────────────────────
def fetch_rss_articles():
    seen = load_seen()
    new_articles = []

    for source_name, feed_url in RSS_FEEDS.items():
        log.info(f"Fetching {source_name}...")
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                link = entry.get('link', '')
                if not link or link in seen:
                    continue

                title = entry.get('title', '').strip()
                if not title:
                    continue

                try:
                    article = Article(link, language='ar')
                    article.download()
                    article.parse()
                    full_text = article.text.strip()
                except Exception:
                    full_text = entry.get('summary', '').strip()

                if len(full_text) < 100:
                    continue

                new_articles.append({
                    'source': source_name,
                    'title': title,
                    'summary': entry.get('summary', ''),
                    'link': link,
                    'timestamp': entry.get('published', datetime.now().isoformat()),
                    'bucket': 'B_Truth',
                    'full_text': full_text,
                })
                seen.add(link)
                count += 1

            log.info(f"  {source_name}: {count} new articles")
        except Exception as e:
            log.warning(f"  {source_name} FAILED: {e}")

    save_seen(seen)
    return new_articles


# ── Main pipeline ────────────────────────────────────────────────────────────
def run_update():
    start = time.time()

    # 1. Fetch new articles
    articles = fetch_rss_articles()
    if not articles:
        log.info("No new articles found. Done.")
        return

    log.info(f"Fetched {len(articles)} new articles total")

    # 2. Extract propositions
    all_props = []
    for art in articles:
        props = extract_propositions_from_article(
            art['title'], art['full_text'], art['source']
        )
        all_props.extend(props)

    if not all_props:
        log.info("No propositions extracted (articles too short?). Done.")
        return

    df_new = pd.DataFrame(all_props)
    df_new = df_new.drop_duplicates(subset='proposition').reset_index(drop=True)
    log.info(f"Extracted {len(df_new)} new propositions from {len(articles)} articles")

    # 3. Embed with E5
    log.info("Embedding new propositions...")
    vecs = get_embeddings_batch(df_new['proposition'].tolist(), batch_size=32)

    # 4. Add to Chroma (incremental — no rebuild)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col_b = client.get_collection("bucket_b_propositions")
    existing_count = col_b.count()
    log.info(f"Chroma Bucket B currently has {existing_count} docs")

    BATCH = 500
    for i in range(0, len(df_new), BATCH):
        batch_df = df_new.iloc[i:i + BATCH]
        batch_vecs = vecs[i:i + BATCH]
        start_id = existing_count + i
        col_b.add(
            ids=[f"prop_{start_id + j}" for j in range(len(batch_df))],
            embeddings=batch_vecs.tolist(),
            documents=batch_df['proposition'].tolist(),
            metadatas=[{
                "article_id": str(r['article_id']),
                "title": str(r['title']),
                "source": str(r['source']),
            } for _, r in batch_df.iterrows()]
        )

    log.info(f"Chroma updated: {existing_count} → {col_b.count()} docs")

    # 5. Append to propositions CSV (so BM25 rebuilds on notebook startup)
    df_existing = pd.read_csv(PROPS_CSV)
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset='proposition').reset_index(drop=True)
    df_combined.to_csv(PROPS_CSV, index=False)
    log.info(f"Propositions CSV updated: {len(df_existing)} → {len(df_combined)} rows")

    # 6. Append to articles CSV (for TITLE_TO_LINK lookup)
    df_articles = pd.DataFrame(articles)
    df_art_existing = pd.read_csv(ARTICLES_CSV)
    df_art_combined = pd.concat([df_art_existing, df_articles], ignore_index=True)
    df_art_combined = df_art_combined.drop_duplicates(subset='title').reset_index(drop=True)
    df_art_combined.to_csv(ARTICLES_CSV, index=False)
    log.info(f"Articles CSV updated: {len(df_art_existing)} → {len(df_art_combined)} rows")

    elapsed = time.time() - start
    log.info(f"✅ Update complete in {elapsed:.1f}s — "
             f"+{len(articles)} articles, +{len(df_new)} propositions")


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Bucket B incremental update — starting")
    log.info("=" * 60)
    try:
        run_update()
    except Exception as e:
        log.error(f"Update failed: {e}", exc_info=True)
        sys.exit(1)
