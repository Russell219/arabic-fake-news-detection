"""
Saheeh Masr (saheeh.news) scraper — Drupal node crawler
Run: python3 -u scrape_saheeh.py
"""

import time, random, pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

OUTPUT = "/Users/russelltamer/Desktop/system 2 RAG/saheeh_masr_claims.csv"

FAKE_KW = ["مضلل","خاطئ","كاذب","مزيف","مفبرك","زائف",
           "غير صحيح","غير دقيق","ادعاء كاذب","معلومة خاطئة",
           "ادعاء مضلل","معلومة مضللة","تصريح مضلل","مبالغ"]
TRUE_KW = ["صحيح","دقيق","مؤكد","تصريح صحيح"]
SKIP_KW = ["من نحن","المنهجية","المدونة","سياسة","أرسل","فريق","تواصل",
           "اشترك","تبرع","الرئيسية","cookies","cookie","toggle","navigation"]

def has_arabic(text):
    """Check if text contains Arabic characters."""
    return any('؀' <= c <= 'ۿ' for c in text)

def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def extract_verdict(text):
    for kw in FAKE_KW:
        if kw in text: return "FALSE"
    for kw in TRUE_KW:
        if kw in text: return "TRUE"
    return "UNKNOWN"

def scrape_node(driver, node_id):
    try:
        driver.get(f"https://www.saheeh.news/ar/node/{node_id}")
        time.sleep(random.uniform(1.2, 2.0))

        cur = driver.current_url
        # Skip 404s and redirects away from article
        if "/ar/node/" not in cur and "/index.php/ar/node/" not in cur:
            return None

        # Get claim from div.statement (Saheeh Masr's structure)
        claim = ""
        for sel in ["div.statement","[class*='statement']","div.claim","[class*='claim']"]:
            el = driver.find_elements(By.CSS_SELECTOR, sel)
            if el:
                claim = el[0].text.strip()
                break

        # Fallback to h2 if no statement div
        if not claim:
            els = driver.find_elements(By.TAG_NAME, "h2")
            for e in els:
                txt = e.text.strip()
                if txt and len(txt) > 10 and "visually-hidden" not in (e.get_attribute("class") or ""):
                    claim = txt
                    break

        if not claim or len(claim) < 8:
            return None
        if not has_arabic(claim):
            return None
        if any(kw.lower() in claim.lower() for kw in SKIP_KW):
            return None

        # Get verdict from page title (format: "تصريح غير دقيق - Person | صحيح مصر")
        verdict = ""
        page_title = driver.title or ""
        for vkw in ["غير دقيق","خاطئ","كاذب","مضلل","مزيف","مفبرك","صحيح","دقيق"]:
            if vkw in page_title:
                verdict = "FALSE" if vkw not in ["صحيح","دقيق"] else "TRUE"
                break

        # Also check verdict label elements
        if not verdict:
            for sel in [".field--name-field-verdict",".verdict","[class*='verdict']",
                        "[class*='rating']",".field--name-field-label"]:
                el = driver.find_elements(By.CSS_SELECTOR, sel)
                if el:
                    verdict = el[0].text.strip()
                    break

        # Get body
        desc = ""
        for sel in [".field--name-body p",".node__content p","article p",".content p"]:
            el = driver.find_elements(By.CSS_SELECTOR, sel)
            if el:
                desc = " ".join(e.text for e in el[:3]).strip()
                break

        # Get date
        date = ""
        for sel in ["time[datetime]",".field--name-created"]:
            el = driver.find_elements(By.CSS_SELECTOR, sel)
            if el:
                date = el[0].get_attribute("datetime") or el[0].text
                break

        if not verdict:
            verdict = extract_verdict(claim + " " + desc)

        return {"node_id": node_id, "claim": claim, "verdict": verdict,
                "description": desc[:400], "date": date,
                "url": f"https://www.saheeh.news/ar/node/{node_id}",
                "source": "saheeh_masr"}
    except:
        return None

def main():
    print("Starting Saheeh Masr crawler (nodes 1-3500)...")
    driver = make_driver()
    results = []

    try:
        for node_id in range(1, 3501):
            r = scrape_node(driver, node_id)
            if r:
                results.append(r)
                print(f"✅ [{node_id}] {r['verdict']:8} | {r['claim'][:65]}")
            elif node_id % 100 == 0:
                print(f"... {node_id}/3500 checked | {len(results)} articles found so far")

            if len(results) > 0 and len(results) % 30 == 0:
                pd.DataFrame(results).to_csv(OUTPUT, index=False, encoding="utf-8-sig")
                print(f"💾 Saved {len(results)} articles")

            if node_id % 200 == 0:
                time.sleep(random.uniform(3, 5))
    finally:
        driver.quit()

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"\n✅ DONE: {len(results)} articles → {OUTPUT}")
    if len(df):
        print(df['verdict'].value_counts())

if __name__ == "__main__":
    main()
