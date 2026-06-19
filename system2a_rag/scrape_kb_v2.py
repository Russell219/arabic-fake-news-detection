"""
scrape_kb_v2.py
---------------
Builds an expanded Arabic Knowledge Base for Bucket B.

Sources:
  1. Wikipedia Arabic  — encyclopedic facts, clean text, topic-based
  2. AlJazeera archive — 2015+, paginated archive
  3. BBC Arabic        — 2015+, topic RSS feeds
  4. Al-Ahram          — 2015+, Egyptian news
  5. Additional RSS    — new feeds not in original scraper

Output: kb_articles_v2.csv
  Columns: source, title, summary, link, timestamp, full_text

Run this script, then run clean_fulltext.py on the output,
then run extract_propositions.py to get df_propositions_v2.csv.
"""

import time
import re
import requests
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

OUTPUT_CSV   = "kb_articles_v2.csv"
DELAY        = 3.0          # seconds between requests (Wikipedia needs ≥3s)
MIN_DATE     = 2015         # skip articles older than this year
MIN_TEXT_LEN = 150          # skip articles with less content than this

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def safe_get(url: str, timeout: int = 15, retries: int = 3) -> requests.Response | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"    ⏳ Rate limited — waiting {wait}s…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            if attempt < retries - 1:
                time.sleep(5)
            else:
                print(f"    ⚠ GET failed: {url[:60]} — {e}")
        except Exception as e:
            print(f"    ⚠ GET failed: {url[:60]} — {e}")
            return None
    return None


def clean_text(text: str) -> str:
    """Basic cleanup: collapse whitespace, strip control chars."""
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def extract_year(date_str: str) -> int:
    """Try to parse a year from various date formats."""
    if not date_str:
        return 9999
    m = re.search(r'(20\d{2})', str(date_str))
    return int(m.group(1)) if m else 9999


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — Wikipedia Arabic
# ═══════════════════════════════════════════════════════════════════════════════

# Direct article titles — no search API needed, one request per article
WIKI_ARTICLES = [
    # Health
    "فيروس كورونا المستجد", "كوفيد-19", "لقاح كوفيد-19", "جائحة فيروس كورونا",
    "لقاح", "إيبولا", "الإنفلونزا", "الملاريا", "السرطان", "مرض السكري", "الإيدز",
    "الجدري", "متحور أوميكرون", "الصحة العامة", "منظمة الصحة العالمية",
    # Palestine / Israel
    "قطاع غزة", "الضفة الغربية", "حركة حماس", "حزب الله", "النزاع الفلسطيني الإسرائيلي",
    "القدس", "محمود عباس", "بنيامين نتنياهو", "وكالة الأونروا",
    "الجيش الإسرائيلي", "عملية طوفان الأقصى", "حرب غزة 2023",
    "فلسطين", "إسرائيل", "حل الدولتين", "مستوطنات إسرائيلية",
    "حركة فتح", "السلطة الفلسطينية",
    # Egypt
    "عبد الفتاح السيسي", "محمد مرسي", "الإخوان المسلمون في مصر",
    "ثورة 25 يناير", "اقتصاد مصر", "الجنيه المصري", "قناة السويس",
    "شبه جزيرة سيناء", "الأزهر الشريف", "البنك المركزي المصري",
    "مجلس النواب المصري", "الدستور المصري", "انتخابات مصر",
    "مصر", "القاهرة", "الإسكندرية", "دعم الطاقة في مصر",
    # Arab world
    "الحرب في اليمن", "الحرب الأهلية السورية", "الأزمة السودانية",
    "الحرب الأهلية الليبية", "حرب لبنان 2006", "ثورات الربيع العربي",
    "تونس", "المغرب", "الجزائر", "العراق", "سوريا", "لبنان", "السودان",
    "الأزمة الليبية", "داعش", "تنظيم القاعدة",
    # International
    "دونالد ترامب", "جو بايدن", "فلاديمير بوتين", "الغزو الروسي لأوكرانيا",
    "حلف شمال الأطلسي", "الأمم المتحدة", "العقوبات الاقتصادية",
    "إيران", "البرنامج النووي الإيراني", "الحرس الثوري الإيراني",
    "المملكة العربية السعودية", "محمد بن سلمان", "قطر", "تركيا", "رجب طيب أردوغان",
    "الصين", "الولايات المتحدة", "روسيا", "الاتحاد الأوروبي",
    "اتفاقيات أبراهام", "التطبيع العربي الإسرائيلي",
    # Economy
    "التضخم الاقتصادي", "الدولار الأمريكي", "أسعار النفط", "أوبك",
    "بيتكوين", "العملات المشفرة", "البطالة", "الفقر",
    "صندوق النقد الدولي", "البنك الدولي", "الديون السيادية",
    "أسعار الغذاء العالمية", "الأمن الغذائي",
    # Technology / Disinformation
    "الذكاء الاصطناعي", "فيسبوك", "تويتر", "تيك توك", "واتساب",
    "التضليل الإعلامي", "الأخبار المزيفة", "وسائل التواصل الاجتماعي",
    "التشفير الرقمي", "الأمن السيبراني",
    # Environment
    "تغير المناخ", "الاحترار العالمي", "الطاقة الشمسية", "الطاقة النووية",
    "نهر النيل", "سد النهضة الإثيوبي", "أزمة المياه",
    # Religion / Egypt-specific
    "الإسلام", "المسيحية القبطية", "الكنيسة القبطية الأرثوذكسية",
    "الأقباط في مصر", "المسجد الأقصى", "الحج",
    # Public health myths (common fake news topics)
    "نظرية المؤامرة", "حرب المعلومات", "الدجل الطبي",
]


def scrape_wikipedia(articles: list) -> list[dict]:
    """
    Fetch Wikipedia Arabic articles directly by title.
    One API call per article — no search step — avoids rate limits.
    """
    rows = []
    seen = set()

    print(f"\n{'='*60}")
    print(f"SOURCE 1: Wikipedia Arabic  ({len(articles)} articles, direct fetch)")
    print(f"{'='*60}")

    for title in articles:
        if title in seen:
            continue
        seen.add(title)

        content_url = (
            "https://ar.wikipedia.org/w/api.php"
            "?action=query&format=json&prop=extracts"
            "&explaintext=true&exsectionformat=plain"
            f"&titles={requests.utils.quote(title)}"
        )
        r = safe_get(content_url)
        if not r:
            time.sleep(DELAY)
            continue

        pages = r.json().get('query', {}).get('pages', {})
        for page in pages.values():
            if page.get('pageid', -1) == -1:   # page doesn't exist
                continue
            extract = page.get('extract', '')
            if not extract or len(extract) < MIN_TEXT_LEN:
                continue

            real_title = page.get('title', title)
            paras    = [p.strip() for p in extract.split('\n') if len(p.strip()) > 50]
            summary  = paras[0] if paras else extract[:300]
            full_text = clean_text(extract[:6000])

            rows.append({
                "source":    "Wikipedia_AR",
                "title":     real_title,
                "summary":   summary[:300],
                "link":      f"https://ar.wikipedia.org/wiki/{requests.utils.quote(real_title)}",
                "timestamp": "2024",
                "full_text": full_text,
            })
            print(f"  ✓ {real_title[:50]}  ({len(full_text)} chars)")

        time.sleep(DELAY)

    print(f"  ✅ Wikipedia: {len(rows)} articles")
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — RSS feeds (extended list)
# ═══════════════════════════════════════════════════════════════════════════════

RSS_FEEDS = {
    # AlJazeera
    "AlJazeera_News":    "https://www.aljazeera.net/xml/rss2.0.xml",
    "AlJazeera_Economy": "https://www.aljazeera.net/economy/feed/rss2",
    "AlJazeera_Science": "https://www.aljazeera.net/science/feed/rss2",
    # BBC Arabic
    "BBC_Arabic":        "https://feeds.bbci.co.uk/arabic/rss.xml",
    "BBC_MiddleEast":    "https://feeds.bbci.co.uk/arabic/middleeast/rss.xml",
    # RT Arabic
    "RT_Arabic":         "https://arabic.rt.com/rss/",
    "RT_MiddleEast":     "https://arabic.rt.com/rss/?tag=%D8%A7%D9%84%D8%B4%D8%B1%D9%82+%D8%A7%D9%84%D8%A3%D9%88%D8%B3%D8%B7",
    # CNN Arabic
    "CNN_Arabic":        "https://arabic.cnn.com/rss/cnn_arabic.rss",
    # France24
    "France24_Arabic":   "https://www.france24.com/ar/rss",
    "France24_MidEast":  "https://www.france24.com/ar/شرق-أوسط/rss",
    # Sky News Arabia
    "SkyNews_Arabia":    "https://www.skynewsarabia.com/feeds/rss.xml",
    # Deutsche Welle Arabic
    "DW_Arabic":         "https://rss.dw.com/rdf/rss-ar-all",
    # Youm7
    "Youm7_Politics":    "https://www.youm7.com/rss/section/1",
    "Youm7_Economy":     "https://www.youm7.com/rss/section/2",
    "Youm7_Health":      "https://www.youm7.com/rss/section/9",
    # Al-Masry Al-Youm
    "AlMasry_Egypt":     "https://www.almasryalyoum.com/rss/rssfeeds",
    # Al-Ahram
    "AlAhram_News":      "https://gate.ahram.org.eg/rss.aspx",
    # Dostor
    "Dostor_News":       "https://www.dostor.org/rss",
    # Sada ElBalad
    "SadaElBalad":       "https://www.elbalad.news/rss",
    # Veto gate
    "Vetogate":          "https://www.vetogate.com/rss",
    # Mada Masr (independent Egyptian)
    "MadaMasr":          "https://www.madamasr.com/ar/feed/",
    # Arab News Arabic
    "ArabNews_AR":       "https://www.arabnews.com/ar/rss.xml",
    # Asharq Al-Awsat
    "AsharqAlAwsat":     "https://aawsat.com/rss/home",
}


def scrape_rss_feeds(feeds: dict) -> list[dict]:
    """Parse all RSS feeds and scrape article body for each entry."""
    rows = []

    print(f"\n{'='*60}")
    print(f"SOURCE 2: RSS Feeds  ({len(feeds)} feeds)")
    print(f"{'='*60}")

    for source, url in feeds.items():
        print(f"  [{source}] {url}")
        try:
            feed = feedparser.parse(url)
            entries = feed.entries
        except Exception as e:
            print(f"    ⚠ Feed parse failed: {e}")
            continue

        count = 0
        for entry in entries:
            # Date filter
            pub = getattr(entry, 'published', '') or getattr(entry, 'updated', '')
            if extract_year(pub) < MIN_DATE:
                continue

            title   = getattr(entry, 'title', '').strip()
            link    = getattr(entry, 'link', '').strip()
            summary = getattr(entry, 'summary', '').strip()
            # Strip HTML from summary
            summary = BeautifulSoup(summary, 'html.parser').get_text()[:400]

            if not title or not link:
                continue

            # Scrape article body
            full_text = scrape_article_body(link)

            rows.append({
                "source":    source,
                "title":     clean_text(title),
                "summary":   clean_text(summary),
                "link":      link,
                "timestamp": pub[:25] if pub else '',
                "full_text": full_text,
            })
            count += 1
            time.sleep(DELAY * 0.4)

        print(f"    → {count} articles")

    print(f"  ✅ RSS total: {len(rows)} articles")
    return rows


def scrape_article_body(url: str) -> str:
    """Extract article body text from a URL."""
    r = safe_get(url)
    if not r:
        return ''
    try:
        soup = BeautifulSoup(r.content, 'html.parser')
        # Remove nav, header, footer, scripts, ads
        for tag in soup(['script', 'style', 'nav', 'header', 'footer',
                         'aside', 'form', 'button', 'figure']):
            tag.decompose()

        # Common article body selectors
        for selector in ['article', '.article-body', '.story-body',
                         '.article__content', '.post-content',
                         '[class*="article"]', '[class*="content"]',
                         '.main-content', 'main']:
            body = soup.select_one(selector)
            if body:
                text = body.get_text(separator=' ')
                text = clean_text(text)
                if len(text) >= MIN_TEXT_LEN:
                    return text[:6000]

        # Fallback: all paragraphs
        paras = soup.find_all('p')
        text  = ' '.join(p.get_text() for p in paras if len(p.get_text()) > 30)
        return clean_text(text)[:6000]
    except Exception:
        return ''


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — AlJazeera archive (paginated, 2015+)
# ═══════════════════════════════════════════════════════════════════════════════

def scrape_aljazeera_archive(max_pages: int = 30) -> list[dict]:
    """
    Scrape AlJazeera Arabic archive pages for articles 2015–now.
    Each page has ~10 articles.
    """
    rows = []
    base_url = "https://www.aljazeera.net/news/category/all/"

    print(f"\n{'='*60}")
    print(f"SOURCE 3: AlJazeera Archive (max {max_pages} pages)")
    print(f"{'='*60}")

    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}" if page > 1 else base_url
        r   = safe_get(url)
        if not r:
            break

        soup  = BeautifulSoup(r.content, 'html.parser')
        links = soup.select('article a[href]') or soup.select('.article-card a[href]')

        if not links:
            # Try generic link extraction
            links = [a for a in soup.find_all('a', href=True)
                     if '/news/' in a['href'] and len(a.get_text(strip=True)) > 10]

        found = 0
        seen  = set()
        for a in links:
            href = a['href']
            if not href.startswith('http'):
                href = 'https://www.aljazeera.net' + href
            if href in seen:
                continue
            seen.add(href)

            title    = a.get_text(strip=True)
            full_text = scrape_article_body(href)
            if len(full_text) < MIN_TEXT_LEN:
                continue

            rows.append({
                "source":    "AlJazeera_Archive",
                "title":     clean_text(title),
                "summary":   full_text[:300],
                "link":      href,
                "timestamp": str(datetime.now().year),
                "full_text": full_text,
            })
            found += 1
            time.sleep(DELAY)

        print(f"  Page {page}: {found} articles  (total: {len(rows)})")
        if found == 0:
            print("  No articles found — stopping")
            break
        time.sleep(DELAY * 2)

    print(f"  ✅ AlJazeera archive: {len(rows)} articles")
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    base = Path(__file__).parent
    all_rows = []

    print("=" * 60)
    print("Arabic KB Scraper v2")
    print("Target: 2015 → now  |  Max variation across sources")
    print("=" * 60)

    # 1. Wikipedia Arabic (biggest, cleanest source)
    wiki_rows = scrape_wikipedia(WIKI_ARTICLES)
    all_rows.extend(wiki_rows)
    print(f"\nRunning total: {len(all_rows)}")

    # 2. RSS feeds
    rss_rows = scrape_rss_feeds(RSS_FEEDS)
    all_rows.extend(rss_rows)
    print(f"\nRunning total: {len(all_rows)}")

    # 3. AlJazeera archive
    aj_rows = scrape_aljazeera_archive(max_pages=30)
    all_rows.extend(aj_rows)
    print(f"\nRunning total: {len(all_rows)}")

    # Build DataFrame
    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset='link').reset_index(drop=True)
    df = df[df['full_text'].str.len() >= MIN_TEXT_LEN].reset_index(drop=True)

    # Stats
    print(f"\n{'='*60}")
    print(f"FINAL: {len(df)} articles")
    print(df['source'].value_counts().to_string())
    print(f"{'='*60}")

    # Save
    out = base / OUTPUT_CSV
    df.to_csv(out, index=False)
    print(f"\n✅ Saved: {out}")
    print(f"\nNext steps:")
    print(f"  1. python3 clean_fulltext.py  (update INPUT_CSV to {OUTPUT_CSV})")
    print(f"  2. python3 extract_propositions.py  (update INPUT_CSV)")
    print(f"  3. Re-ingest Bucket B in notebook")


if __name__ == '__main__':
    main()
