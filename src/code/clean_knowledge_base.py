#!/usr/bin/env python3
"""
Clean the Aramco knowledge base text file for RAG ingestion.

Removes:
  - UI artifacts from web scraping (Learn more, This content is blocked, etc.)
  - Garbled PDF text: single-char lines and interleaved column text
  - [Page N] markers
  - Standalone year-number blocks from timeline components
  - PDF navigation breadcrumb bars
  - Reversed/mirrored text fragments from rotated PDF content
  - Excessive blank lines (collapses to max 2)
  - Pipe/dot-only lines from PDF table borders
"""

import re
from pathlib import Path

INPUT_FILE = "aramco_complete_knowledge_base.txt"
OUTPUT_FILE = "aramco_knowledge_base_clean.txt"

# ── Exact-string UI artifacts to remove ──────────────────────────────────────

UI_ARTIFACTS = {
    "This content is blocked",
    "You need to give permission.",
    "You need to give permission",
    "Update consent",
    "Learn more",
    "Read more",
    "Get started",
    "In this section",
    "Download zip-file",
    "See all reports",
    "See all stories",
    "See all",
    "Key documents",
    "Key Documents",
    "Saudi Aramco: Company General Use",
    "Join us on an interactive journey through time",
    "What we do?",
    "Watch her story",
    "Watch his story",
    "Watch their story",
    "Watch the story",
    "pdf",
    "Clear filters",
    "Apply filters",
    "No results",
    "Show filters",
    "Show all",
    "AND",         # standalone conjunction fragment from broken section headers
}

# ── Regex patterns for lines to drop ─────────────────────────────────────────

ARTIFACT_PATTERNS = [
    re.compile(r"^\[Page \d+\]$"),
    re.compile(r"^Visit the [‘’'“”\"].*[‘’'“”\"] webpage$"),  # curly/straight quotes
    re.compile(r"^For more information see page \d+\.?$"),
    re.compile(r"^Download our \d{4}.*[Rr]eport.*$"),
    re.compile(r"^@\w+$"),                          # @Saudi_Aramco
    re.compile(r"^\d{4}$"),                          # Standalone year (1933, 1935, ...)
    re.compile(r"^[|\.\s]+$"),                       # Only pipe/period/space
    re.compile(r"^\d{4}s?[-–]?\d*s?:\s+\w+"),       # "1940s: Expansion", "1940s-60s: ..." timeline labels
    re.compile(r"^\d+\.\d+MB$"),                     # File sizes like 16.9MB
    re.compile(r"^\d+MB$"),                          # File sizes like 16MB
    # Garbled dot-prefix fragments like ". n a" or ". I"
    re.compile(r"^\.\s+[a-zA-Z](\s+[a-zA-Z])*\s*$"),
    # PDF section navigation bars: start with "1. " or "2. " followed by all-caps section name
    re.compile(r"^[1-9]\.\s+[A-Z][A-Z ]{4,}(?:\s+\d+\.\s+[A-Z])+"),
    # Truncated section-header fragments from PDF layout (e.g. "1. A", "2. R", "3. S")
    re.compile(r"^[1-9]\.\s+[A-Z]$"),
    # Short mixed fragments with punctuation: "'s", "'s l", "e," etc.
    re.compile(r"^['‘’]s(\s+\S{1,2})?$"),   # 's or 's l
    re.compile(r"^[a-zA-Z]{1,2}[,;:]\s*$"),            # "e," "y," "s;" etc.
]

# Reversed forms of common words that appear on their own line from rotated PDFs
# Build as exact reversed look-ups (content.lower() == reversed_of_word)
_COMMON_WORDS_TO_REVERSE = [
    # Stop words / prepositions
    "the", "and", "for", "but", "not", "are", "was", "has", "had", "its",
    "our", "per", "net", "due", "see", "use", "all", "any", "one", "two",
    "may", "can", "new", "big", "low", "end", "set", "of", "or", "if",
    "to", "at", "as", "be", "by", "in", "on", "an", "no",
    # Common industry words that appear individually in rotated PDF pages
    "oil", "gas", "year", "cost", "rate", "risk", "from", "that", "with",
    "this", "also", "into", "over", "than", "then", "when", "were", "will",
    "have", "been", "more", "which", "they", "their", "there", "these",
    # Corporate / financial terms that appear on their own line
    "total", "share", "board", "audit", "value", "notes", "other", "profit",
    "income", "assets", "equity", "capital", "shares", "grants", "granted",
    "short", "long", "term", "plans", "member", "members",
    "director", "chairman", "secretary", "managing", "percentage",
    "remuneration", "remunerations", "periodic", "incentive", "function",
    "company", "aramco", "saudi", "annual", "report",
    "financial", "revenue", "liabilities", "operating", "investing",
    "financing", "depreciation", "amortization", "statement", "balance",
    "contents", "results", "operations", "operational", "testimonials",
    "upstream", "downstream", "production", "capacity", "reserves",
]
_REVERSED_EXACT: set[str] = {w[::-1].lower() for w in _COMMON_WORDS_TO_REVERSE}


def is_garbled(line: str) -> bool:
    """
    True if the line looks like interleaved PDF-column text.
    Two checks:
    1. 8+ tokens where >72% are 1-2 characters long (main garbled detector).
    2. 3-7 tokens where ALL are 1-2 characters (small garbled fragments like "u e to").
    """
    tokens = line.split()
    n = len(tokens)
    if n == 0:
        return False
    short = sum(1 for t in tokens if len(t) <= 2)
    if n >= 8:
        return (short / n) > 0.72
    if 3 <= n <= 7:
        return short == n   # all tokens are 1-2 chars
    return False


def is_short_noise(content: str) -> bool:
    """
    True for lines that carry no information as standalone lines:
    single letters, pure punctuation, standalone page numbers,
    or 2-char all-lowercase fragments (word fragments from garbled PDF).
    """
    if len(content) == 1:
        return True   # any single character
    if re.match(r"^\d{1,2}\.?$", content):     # 1-2 digit page numbers
        return True
    if re.match(r"^[^a-zA-Z0-9]+$", content):  # only punctuation/symbols
        return True
    if re.match(r"^[a-z]{2}$", content):        # 2-char all-lowercase (word fragments)
        return True
    if re.match(r"^[a-z];$", content):          # sentence-end fragments like "s;"
        return True
    return False


def is_reversed_text(content: str) -> bool:
    """
    True for reversed/mirrored text from rotated PDF pages.
    Uses an exact lookup: content must be the reverse of a known common word.
    """
    return content.lower() in _REVERSED_EXACT


def classify_line(raw: str) -> str | None:
    """Return the cleaned line, or None to drop it."""
    stripped = raw.rstrip()
    content = stripped.strip()

    # Blank lines — handled at block level, keep for now
    if not content:
        return stripped

    # Exact UI artifact
    if content in UI_ARTIFACTS:
        return None

    # Regex patterns
    for pat in ARTIFACT_PATTERNS:
        if pat.match(content):
            return None

    # Very short noise
    if is_short_noise(content):
        return None

    # Garbled interleaved-column text
    if is_garbled(content):
        return None

    # Reversed/mirrored text
    if is_reversed_text(content):
        return None

    return stripped


def clean(input_path: Path, output_path: Path) -> None:
    print(f"Reading  {input_path} …")
    lines = input_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"  {len(lines):,} lines in")

    out: list[str] = []
    blank_run = 0
    removed = 0

    for raw in lines:
        result = classify_line(raw)

        if result is None:
            removed += 1
            # Don't collapse content into a wall of text; ensure at most one blank
            # where a removed line used to separate paragraphs.
            if out and out[-1] != "":
                blank_run += 1
                if blank_run <= 1:
                    out.append("")
            continue

        if result == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
        else:
            blank_run = 0
            out.append(result)

    # Strip leading/trailing blank lines
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    output_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    kept = len(out)
    print(f"  {kept:,} lines out  ({removed:,} removed, {len(lines)-kept:,} net reduction)")
    print(f"Wrote  {output_path}")


if __name__ == "__main__":
    base = Path(__file__).parent
    clean(base / INPUT_FILE, base / OUTPUT_FILE)
