"""
Saudi Aramco RAG Data Crawler
Crawls public Aramco pages, annual reports, careers, and related content
Saves output as JSON and plain text for RAG ingestion
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse

# ─── Config ───────────────────────────────────────────────────────────────────

OUTPUT_DIR = "aramco_rag_data"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RAG-Crawler/1.0)"
}
DELAY = 2  # seconds between requests (be polite)

# Target URLs to crawl
TARGETS = [
    # About & Company Info
    "https://www.aramco.com/en/about-us",
    "https://www.aramco.com/en/about-us/our-history",
    "https://www.aramco.com/en/about-us/leadership",
    "https://www.aramco.com/en/about-us/our-values",
    "https://www.aramco.com/en/about-us/our-business",

    # Careers
    "https://www.aramco.com/en/careers",
    "https://www.aramco.com/en/careers/working-here",
    "https://www.aramco.com/en/careers/students-and-graduates",
    "https://www.aramco.com/en/careers/hiring-process",

    # Operations & Business
    "https://www.aramco.com/en/our-business/upstream",
    "https://www.aramco.com/en/our-business/downstream",
    "https://www.aramco.com/en/our-business/chemicals",
    "https://www.aramco.com/en/our-business/shipping",

    # Sustainability & Innovation
    "https://www.aramco.com/en/sustainability",
    "https://www.aramco.com/en/innovation",

    # News (good for interview current affairs)
    "https://www.aramco.com/en/news-media/news",
]

# Annual reports page
ANNUAL_REPORTS_URL = "https://www.aramco.com/en/investors/reports-and-presentations"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_text(text):
    """Clean and normalize text."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def scrape_page(url):
    """Scrape a single page and return cleaned text + metadata."""
    try:
        print(f"  Scraping: {url}")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        # Get page title
        title = soup.title.string.strip() if soup.title else url

        # Get main content — try common content containers first
        content = ""
        for selector in ["main", "article", "#content", ".content", ".main-content", "body"]:
            element = soup.select_one(selector)
            if element:
                content = clean_text(element.get_text(separator="\n"))
                break

        if not content:
            content = clean_text(soup.get_text(separator="\n"))

        return {
            "url": url,
            "title": title,
            "content": content,
            "word_count": len(content.split())
        }

    except Exception as e:
        print(f"  ❌ Failed {url}: {e}")
        return None


def find_pdf_links(url):
    """Find PDF download links on a page (for annual reports)."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        pdfs = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".pdf" in href.lower():
                full_url = urljoin(url, href)
                pdfs.append({
                    "text": a.get_text(strip=True),
                    "url": full_url
                })
        return pdfs
    except Exception as e:
        print(f"  ❌ Failed to find PDFs on {url}: {e}")
        return []


# ─── Main Crawler ─────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_data = []
    failed = []

    print("=" * 60)
    print("Saudi Aramco RAG Data Crawler")
    print("=" * 60)

    # 1. Crawl target pages
    print("\n📄 Crawling Aramco pages...\n")
    for url in TARGETS:
        result = scrape_page(url)
        if result and result["word_count"] > 50:
            all_data.append(result)
            print(f"  ✅ {result['title']} ({result['word_count']} words)")
        else:
            failed.append(url)
        time.sleep(DELAY)

    # 2. Find annual report PDFs
    print("\n📊 Looking for Annual Reports...\n")
    pdfs = find_pdf_links(ANNUAL_REPORTS_URL)
    if pdfs:
        print(f"  Found {len(pdfs)} PDF links:")
        for pdf in pdfs:
            print(f"  📎 {pdf['text']} → {pdf['url']}")
        # Save PDF links separately
        with open(f"{OUTPUT_DIR}/annual_report_pdfs.json", "w") as f:
            json.dump(pdfs, f, indent=2)
        print(f"\n  PDF links saved to {OUTPUT_DIR}/annual_report_pdfs.json")

    # 3. Save all scraped data as JSON
    json_path = f"{OUTPUT_DIR}/aramco_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ JSON saved: {json_path}")

    # 4. Save as plain text (good for RAG chunking)
    txt_path = f"{OUTPUT_DIR}/aramco_data.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(f"URL: {item['url']}\n")
            f.write(f"TITLE: {item['title']}\n")
            f.write("-" * 40 + "\n")
            f.write(item["content"])
            f.write("\n\n" + "=" * 60 + "\n\n")
    print(f"✅ Text saved: {txt_path}")

    # 5. Summary
    print("\n" + "=" * 60)
    print(f"✅ Successfully scraped: {len(all_data)} pages")
    print(f"❌ Failed: {len(failed)} pages")
    total_words = sum(d["word_count"] for d in all_data)
    print(f"📝 Total words collected: {total_words:,}")
    print(f"📁 Output folder: {OUTPUT_DIR}/")
    print("=" * 60)

    if failed:
        print("\nFailed URLs:")
        for url in failed:
            print(f"  - {url}")


if __name__ == "__main__":
    main()