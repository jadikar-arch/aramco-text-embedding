"""
PDF to Text Converter for RAG
Converts all PDF files in a folder to plain text
Handles both text-based and scanned PDFs
Output is saved as .txt files ready for RAG chunking
"""

import os
import json
import pdfplumber
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

PDF_DIR = "."             # folder where your PDFs are (change this)
OUTPUT_DIR = "pdf_texts"  # where text files will be saved

# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF using pdfplumber."""
    text_pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  Pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_pages.append(f"[Page {i+1}]\n{page_text.strip()}")
        return "\n\n".join(text_pages)
    except Exception as e:
        print(f"  ❌ pdfplumber failed: {e}")
        return None


def clean_text(text):
    """Basic text cleanup."""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Find all PDFs
    pdf_files = list(Path(PDF_DIR).glob("**/*.pdf"))

    if not pdf_files:
        print(f"❌ No PDF files found in '{PDF_DIR}'")
        print("  Make sure your PDFs are in the same folder as this script")
        return

    print("=" * 60)
    print(f"PDF to Text Converter")
    print(f"Found {len(pdf_files)} PDF files")
    print("=" * 60)

    results = []
    failed = []

    for pdf_path in pdf_files:
        print(f"\n📄 Processing: {pdf_path.name}")

        raw_text = extract_text_from_pdf(pdf_path)
        text = clean_text(raw_text)

        if not text or len(text.strip()) < 100:
            print(f"  ⚠️  Little/no text extracted — PDF may be scanned")
            print(f"  💡 Try OCR: pip install pytesseract pdf2image")
            failed.append(str(pdf_path))
            continue

        word_count = len(text.split())
        print(f"  ✅ Extracted {word_count:,} words")

        # Save as .txt
        output_name = pdf_path.stem + ".txt"
        output_path = os.path.join(OUTPUT_DIR, output_name)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"SOURCE: {pdf_path.name}\n")
            f.write("=" * 60 + "\n\n")
            f.write(text)

        results.append({
            "source": pdf_path.name,
            "output": output_name,
            "word_count": word_count,
            "pages": text.count("[Page ")
        })

    # Save summary JSON
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print(f"✅ Successfully converted: {len(results)} PDFs")
    print(f"❌ Failed/scanned:         {len(failed)} PDFs")
    total_words = sum(r["word_count"] for r in results)
    print(f"📝 Total words:            {total_words:,}")
    print(f"📁 Output folder:          {OUTPUT_DIR}/")
    print("=" * 60)

    if failed:
        print("\n⚠️  These PDFs had no extractable text (likely scanned):")
        for f in failed:
            print(f"  - {f}")
        print("\n  To handle scanned PDFs:")
        print("  pip install pytesseract pdf2image")
        print("  brew install tesseract  # on Mac")


if __name__ == "__main__":
    main()