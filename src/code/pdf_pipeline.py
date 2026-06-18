"""
Saudi Aramco PDF Pipeline
Downloads PDFs from annual_report_pdfs.json, extracts text with pdfplumber,
and saves clean .txt files ready for OpenWebUI RAG knowledge base ingestion.

Document priority (high → low):
  annual_report    - Full ARA (Integrated Annual Report) ~300 pages
  full_financials  - Full year financial statements
  press_release    - Quarterly/annual results press releases (dense numbers)
  interim_report   - Quarterly interim reports
  webcast_script   - Webcast presentation scripts (text-heavy)
  non_ifrs         - Non-IFRS reconciliation tables
  other            - Everything else

Skipped: webcast slide decks (sparse text), IPO docs (not relevant for ops demo)
"""

import json
import os
import re
import time
import requests
import pdfplumber
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

JSON_PATH       = "aramco_rag_data/annual_report_pdfs.json"
DOWNLOAD_DIR    = "pdf_downloads"
OUTPUT_DIR      = "pdf_texts"
KB_FILE         = "pdf_texts/aramco_knowledge_base.txt"
DELAY           = 1.5   # seconds between downloads (be polite)
MIN_WORDS       = 100   # skip pages with fewer words

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AramcoRAG/1.0)"
}

# Doc types to SKIP (slides have ~10 words per slide, IPO docs not relevant)
SKIP_PATTERNS = [
    "webcast-presentation-english",   # slide decks
    "webcast-presentation-script",    # webcast scripts (redundant with press release)
    "price-announcement",
    "final-price-announcement",
    "public-offering-faq",
    "intention-to-float",
    "prospectus",
    "listed-on-tadawul",
    "stabilisation",
    "corporate-overview",             # marketing overview, not financial
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def classify_doc(url: str) -> tuple[str, str]:
    """Return (doc_type, label) from the URL."""
    u = url.lower()
    # Extract year and period from URL path
    year_match = re.search(r"/(20\d\d)/", u)
    year = year_match.group(1) if year_match else "unknown"

    if "ara-" in u and "english" in u:
        period = re.search(r"ara-(\d{4})", u)
        label = f"Annual_Report_{period.group(1) if period else year}"
        return "annual_report", label
    if "full-financials" in u:
        period = re.search(r"/(fy|q[1-4]|h1|q2---h1|q4---fy)/", u)
        p = (period.group(1) if period else "fy").upper().replace("---", "_")
        return "full_financials", f"Full_Financials_{year}_{p}"
    if "press-release" in u or "financials-press-release" in u:
        period = re.search(r"/(fy|q[1-4]|h1|q2---h1|q4---fy)/", u)
        p = (period.group(1) if period else "fy").upper().replace("---", "_")
        return "press_release", f"Press_Release_{year}_{p}"
    if "interim-report" in u:
        period = re.search(r"/(fy|q[1-4]|h1|q2---h1|q4---fy)/", u)
        p = (period.group(1) if period else "q").upper().replace("---", "_")
        return "interim_report", f"Interim_Report_{year}_{p}"
    if "non-ifrs" in u:
        period = re.search(r"/(fy|q[1-4]|h1|q2---h1|q4---fy)/", u)
        p = (period.group(1) if period else "fy").upper().replace("---", "_")
        return "non_ifrs", f"Non_IFRS_{year}_{p}"
    if "webcast-presentation-script" in u:
        period = re.search(r"/(fy|q[1-4]|h1|q2---h1|q4---fy)/", u)
        p = (period.group(1) if period else "fy").upper().replace("---", "_")
        return "webcast_script", f"Webcast_Script_{year}_{p}"
    return "other", Path(url).stem


def should_skip(url: str) -> bool:
    u = url.lower()
    return any(pat in u for pat in SKIP_PATTERNS)


def download_pdf(url: str, dest: Path) -> bool:
    if dest.exists():
        print(f"  [cached] {dest.name}")
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"  [downloaded] {dest.name} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"  [FAILED] {url}: {e}")
        if dest.exists():
            dest.unlink()
        return False


def extract_text(pdf_path: Path) -> str:
    """Extract text from all pages with pdfplumber."""
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and len(text.split()) >= MIN_WORDS:
                    # Preserve tables by extracting them separately
                    tables = page.extract_tables()
                    table_text = ""
                    for table in tables:
                        rows = []
                        for row in table:
                            clean_row = [cell.strip() if cell else "" for cell in row]
                            rows.append(" | ".join(clean_row))
                        table_text += "\n".join(rows) + "\n"

                    combined = text.strip()
                    if table_text.strip():
                        combined += "\n\n[TABLE DATA]\n" + table_text.strip()
                    pages.append(f"[Page {i}]\n{combined}")
    except Exception as e:
        print(f"  [ERROR] pdfplumber: {e}")
    return "\n\n".join(pages)


def clean(text: str) -> str:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(JSON_PATH) as f:
        raw = json.load(f)

    # Deduplicate URLs (JSON has many empty-label duplicates)
    seen_urls = set()
    unique = []
    for item in raw:
        url = item["url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append(item)

    print(f"Total PDF links: {len(raw)} → deduplicated: {len(unique)}")

    # Classify and filter
    docs = []
    skipped = []
    for item in unique:
        url = item["url"]
        if should_skip(url):
            skipped.append(url)
            continue
        doc_type, label = classify_doc(url)
        docs.append({"url": url, "type": doc_type, "label": label})

    print(f"Skipped (slides/IPO): {len(skipped)}")
    print(f"Queued for extraction: {len(docs)}\n")

    # Sort: annual reports first, then financials, then press releases, interims
    type_order = {
        "annual_report": 0,
        "full_financials": 1,
        "press_release": 2,
        "interim_report": 3,
        "webcast_script": 4,
        "non_ifrs": 5,
        "other": 6,
    }
    docs.sort(key=lambda d: (type_order.get(d["type"], 9), d["label"]))

    kb_parts = []
    results = []
    failed = []

    for doc in docs:
        url = doc["url"]
        label = doc["label"]
        doc_type = doc["type"]
        pdf_path = Path(DOWNLOAD_DIR) / f"{label}.pdf"
        txt_path = Path(OUTPUT_DIR) / f"{label}.txt"

        print(f"\n{'─'*60}")
        print(f"[{doc_type.upper()}] {label}")

        # Skip if text already extracted
        if txt_path.exists():
            print(f"  [cached txt] {txt_path.name}")
            text = txt_path.read_text(encoding="utf-8")
            word_count = len(text.split())
            results.append({"label": label, "words": word_count, "type": doc_type})
            kb_parts.append(text)
            continue

        # Download
        ok = download_pdf(url, pdf_path)
        if not ok:
            failed.append(label)
            continue

        time.sleep(DELAY)

        # Extract
        print(f"  Extracting text...")
        raw_text = extract_text(pdf_path)
        text = clean(raw_text)

        if len(text.split()) < MIN_WORDS:
            print(f"  [WARNING] Very little text extracted — PDF may be scanned/image-based")
            failed.append(label)
            continue

        word_count = len(text.split())
        pages = text.count("[Page ")
        print(f"  Extracted {word_count:,} words across {pages} pages")

        # Build document header for RAG context
        header = (
            f"SOURCE: Saudi Aramco — {label.replace('_', ' ')}\n"
            f"TYPE: {doc_type.replace('_', ' ').title()}\n"
            f"URL: {url}\n"
            f"{'='*60}\n\n"
        )
        full_text = header + text

        # Save individual file
        txt_path.write_text(full_text, encoding="utf-8")
        print(f"  Saved: {txt_path.name}")

        kb_parts.append(full_text)
        results.append({"label": label, "words": word_count, "pages": pages, "type": doc_type})

    # Save consolidated knowledge base
    separator = "\n\n" + "=" * 80 + "\n\n"
    kb_content = separator.join(kb_parts)
    Path(KB_FILE).write_text(kb_content, encoding="utf-8")
    kb_size_mb = Path(KB_FILE).stat().st_size / (1024 * 1024)

    # Summary
    print(f"\n{'='*60}")
    print(f"DONE")
    print(f"  Extracted:  {len(results)} documents")
    print(f"  Failed:     {len(failed)}")
    total_words = sum(r["words"] for r in results)
    print(f"  Total words: {total_words:,}")
    print(f"  Knowledge base: {KB_FILE} ({kb_size_mb:.1f} MB)")
    print(f"  Individual files: {OUTPUT_DIR}/")
    print(f"{'='*60}")

    if failed:
        print(f"\nFailed documents:")
        for f in failed:
            print(f"  - {f}")

    print(f"\nDocument breakdown:")
    by_type = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)
    for t, docs_list in sorted(by_type.items(), key=lambda x: type_order.get(x[0], 9)):
        total = sum(d["words"] for d in docs_list)
        print(f"  {t:20s}: {len(docs_list):3d} docs, {total:>10,} words")


if __name__ == "__main__":
    main()
