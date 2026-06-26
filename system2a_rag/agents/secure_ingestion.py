"""
secure_ingestion.py — Security-hardened RSS ingestion for the RAG pipeline.

Drop-in replacement for the original ``ingest_truth_bucket_robust`` function
in System2_RAG_KB_Ingestion_Pipeline.

Changes vs. the original:
  - Every URL is validated by SecurityValidator BEFORE any request is made.
  - Redirects are manually validated; open redirects are blocked and logged.
  - SSL verification is always enforced.
  - Each article row is enriched with ``credibility`` and ``credibility_label``
    columns from TrustAgent so the frontend can display source trust scores.

Usage (replace the original call with):

    from agents.secure_ingestion import secure_ingest_truth_bucket

    df_kb_truth = secure_ingest_truth_bucket(NEWS_SOURCES)
"""

import time
import random
from datetime import datetime

import feedparser
import pandas as pd

from agents.security_validator import SecurityValidator, SecurityError
from agents.trust_database import TrustAgent

# ---------------------------------------------------------------------------
# Shared instances (stateless — safe to share across calls)
# ---------------------------------------------------------------------------
_trust_agent = TrustAgent()

# User-Agent pool (keeps the original notebook's stealth behaviour)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]


# ---------------------------------------------------------------------------
# Secure ingestion function
# ---------------------------------------------------------------------------

def secure_ingest_truth_bucket(
    sources: dict[str, str],
    delay_range: tuple[float, float] = (1.0, 2.0),
    timeout: int = 10,
) -> pd.DataFrame:
    """
    Ingest RSS feeds from ``sources`` with full security validation.

    For each source URL:
      1. SecurityValidator normalises and whitelists the URL.
      2. A hardened HTTP GET is performed (no auto-redirects, SSL enforced).
      3. Any redirect hops are validated against the whitelist.
      4. feedparser parses the validated response bytes.
      5. TrustAgent enriches every article row with a credibility score.

    Args:
        sources     : NEWS_SOURCES dict (name → RSS URL).
        delay_range : (min, max) seconds to sleep between requests.
        timeout     : Per-request timeout in seconds.

    Returns:
        DataFrame with columns:
            source, title, summary, link, timestamp, bucket,
            credibility, credibility_label
    """
    validator = SecurityValidator(sources, timeout=timeout)
    all_data: list[dict] = []

    print(f"🔒 Secure Ingestion started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Whitelist: {len(validator._whitelist)} trusted domains\n")

    for name, url in sources.items():
        # ── 1. Pre-flight security check ──────────────────────────────
        if not validator.is_allowed(url):
            print(f"🚫 BLOCKED (pre-flight): {name} — hostname not whitelisted")
            continue

        try:
            print(f"📡 Fetching: {name}")
            headers = {
                "User-Agent": random.choice(_USER_AGENTS),
                "Referer":    "https://www.google.com/",
            }

            # ── 2. Security-hardened fetch ─────────────────────────────
            # SecurityValidator.safe_fetch():
            #   - allow_redirects=False (manual redirect validation)
            #   - verify=True  (SSL enforced)
            #   - redirect hops checked against whitelist
            response = validator.safe_fetch(url, headers=headers)

            if response.status_code != 200:
                print(f"⚠️  HTTP {response.status_code}: {name} — skipping")
                continue

            # ── 3. Parse feed from validated response bytes ────────────
            feed = feedparser.parse(response.content)

            if not feed.entries:
                print(f"⚠️  Zero entries: {name}")
                continue

            # ── 4. Enrich with trust metadata ──────────────────────────
            credibility       = _trust_agent.get_credibility(name)
            credibility_label = _trust_agent.credibility_label(name)

            for entry in feed.entries:
                all_data.append({
                    "source":            name,
                    "title":             entry.get("title", ""),
                    "summary":           entry.get("summary", "Summary not available"),
                    "link":              entry.get("link", ""),
                    "timestamp":         entry.get("published", datetime.now().strftime("%Y-%m-%d")),
                    "bucket":            "B_Truth",
                    # Trust framework columns (displayed in frontend)
                    "credibility":       credibility,
                    "credibility_label": credibility_label,
                })

            print(
                f"✅  {name}: {len(feed.entries)} articles "
                f"| credibility={credibility:.2f} ({credibility_label})"
            )

        except SecurityError as exc:
            # Already logged as structured JSON inside SecurityValidator.
            print(f"🚫 SECURITY BLOCK: {name} — {exc}")

        except Exception as exc:
            print(f"❌ Error: {name} — {exc}")

        finally:
            # Polite delay between requests
            time.sleep(random.uniform(*delay_range))

    df = pd.DataFrame(all_data)
    print(f"\n✅ Secure ingestion complete. Total articles: {len(df)}")
    return df
