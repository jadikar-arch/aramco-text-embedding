# Aramco Mini LLM

A Retrieval-Augmented Generation (RAG) pipeline that builds a searchable knowledge base from Saudi Aramco's public financial documents and deploys it as a tool inside [Open WebUI](https://github.com/open-webui/open-webui).

## What it does

The project has three distinct stages:

**1. Data collection** — Two scripts gather raw content:
- `scraper.py` crawls Aramco's public website (About Us, Careers, Operations, Sustainability, News) and saves the text as JSON and plain text for RAG ingestion.
- `pdf_pipeline.py` reads the list of PDF links found by the scraper, downloads every relevant financial document (annual reports, full financials, press releases, interim reports, Non-IFRS reconciliations), extracts text with `pdfplumber`, and assembles a single consolidated knowledge base file.

**2. Cleaning** — `clean_knowledge_base.py` post-processes the raw extracted text to remove noise that would degrade retrieval quality: UI button artifacts from web scraping, garbled interleaved-column text from multi-column PDFs, reversed/mirrored text from rotated PDF pages, page-number lines, standalone punctuation, and timeline labels.

**3. RAG tool** — `aramco_rag_tool.py` is an Open WebUI custom tool. When loaded into Open WebUI, it exposes a `search_knowledge_base` function that:
1. Embeds the user's query with OpenAI `text-embedding-3-small`.
2. Queries a PostgreSQL + pgvector database (hosted on Railway) using cosine similarity.
3. Returns the top-K most relevant chunks with their similarity scores, ready for the LLM to synthesize.

## Document coverage

The knowledge base spans **2017 – 2026** and includes:

| Document type | Description |
|---|---|
| Annual Reports | Full integrated annual reports (~300 pages each) |
| Full Financials | Year-end full financial statements |
| Press Releases | Quarterly and annual results press releases |
| Interim Reports | Q1, H1, Q3 interim financial reports |
| Non-IFRS | Non-IFRS reconciliation tables |

Slide decks, IPO prospectuses, and marketing overviews are intentionally excluded — they contain sparse text that hurts retrieval quality.

## Project layout

```
src/
  code/
    scraper.py               # Step 1a: crawl Aramco website pages
    pdf_pipeline.py          # Step 1b: download PDFs and extract text
    clean_knowledge_base.py  # Step 2: clean the raw knowledge base
    aramco_rag_tool.py       # Step 3: Open WebUI RAG tool
    embed_to_openwebui.ipynb # Notebook: embed chunks into pgvector
  input_data/
    *.pdf                    # Downloaded Aramco PDFs (not committed)
    aramco_rag_data/         # Scraped JSON and text output
  output_data/
    *.txt                    # Per-document extracted text files
    aramco_knowledge_base.txt        # Consolidated raw knowledge base
    aramco_knowledge_base_clean.txt  # Cleaned knowledge base (RAG-ready)
```

## Setup

This project uses [uv](https://docs.astral.sh/uv/) and requires Python 3.13+.

```bash
# Install dependencies
uv sync

# Or with pip
pip install requests beautifulsoup4 pdfplumber openai psycopg2-binary pydantic
```

## Running the pipeline

```bash
# Step 1a — Scrape Aramco website pages
python src/code/scraper.py

# Step 1b — Download PDFs and extract text
#   (requires annual_report_pdfs.json from the scraper output)
python src/code/pdf_pipeline.py

# Step 2 — Clean the knowledge base
python src/code/clean_knowledge_base.py
```

After cleaning, upload `aramco_knowledge_base_clean.txt` to Open WebUI as a knowledge collection (or embed it via the notebook), then load `aramco_rag_tool.py` as a custom tool.

## Open WebUI tool configuration

The `aramco_rag_tool.py` tool has configurable valves inside Open WebUI:

| Valve | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI key for query embedding |
| `DB_URL` | PostgreSQL connection string (Railway) |
| `COLLECTION_NAME` | Open WebUI knowledge collection UUID |
| `EMBEDDING_MODEL` | Must match the model used to build the index (default: `text-embedding-3-small`) |
| `TOP_K` | Number of chunks to return per query (default: 6) |

## Tech stack

- **Python 3.13** with uv for dependency management
- **pdfplumber** — PDF text and table extraction
- **BeautifulSoup4** — web scraping
- **OpenAI** — query embedding (`text-embedding-3-small`)
- **PostgreSQL + pgvector** — vector similarity search (hosted on Railway)
- **Open WebUI** — chat interface and tool host
