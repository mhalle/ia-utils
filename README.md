# ia-utils

A command-line tool for working with Internet Archive books and documents. Build searchable SQLite databases from OCR content, download pages and PDFs, and search across your local catalog.

## Features

- **Search Internet Archive** - Query IA metadata with filters for year, creator, subject, collection, language, and more
- **Create local catalogs** - Build SQLite databases from any IA document with OCR (searchtext, hOCR, or DjVu)
- **Full-text search** - Search OCR text with FTS5 support for phrases, boolean operators, and proximity queries
- **Download pages** - Get individual pages or batches as JPG/PNG/JP2, with optional image processing
- **Download PDFs** - Fetch PDFs directly from Internet Archive
- **Flexible output** - Export results as table, JSON, JSONL, CSV, or key-value records

## Installation

Requires Python 3.9+ and [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/mhalle/ia-utils.git
cd ia-utils
uv sync
```

## Quick Start

```bash
# 1. Search for books on Internet Archive
uv run ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts

# 2. Create a searchable catalog from a document
uv run ia-utils create-catalog anatomicalatlasi00smit -d ./catalogs/

# 3. Search the catalog by OCR text
uv run ia-utils search-catalog -c catalogs/book.sqlite -q "femur"

# 4. Download a page or PDF
uv run ia-utils get-page -c catalogs/book.sqlite -l 42 -o page.jpg
uv run ia-utils get-pdf -c catalogs/book.sqlite
```

## Commands

### Discovery

#### `search-ia` - Search Internet Archive

Search IA metadata using Lucene query syntax with powerful filters:

```bash
# Full-text search with year range
ia-utils search-ia -q "mechanical engineering" --year 1900-1950 -m texts

# Filter by creator and subject
ia-utils search-ia --creator "Darwin" --subject "evolution" --has-ocr

# Browse a collection
ia-utils search-ia -c wellcomelibrary --has-ocr -m texts -l 50

# Export to CSV
ia-utils search-ia -q "botany" -o results.csv

# Get specific fields as JSONL (for scripting)
ia-utils search-ia --subject "anatomy" -f identifier -f title --output-format jsonl
```

**Filters:**
- `--year` - Year or range: `1900`, `1900-1950`, `1900-` (after), `-1950` (before)
- `--creator` - Author/creator name
- `--subject` - Subject/topic
- `--source` - Contributing library
- `--collection` / `-c` - IA collection (e.g., `medicallibrary`)
- `--media-type` / `-m` - texts, audio, movies, image, software, collection
- `--language` / `--lang` - Language code (eng, ger, fre, etc.)
- `--format` / `-F` - File format (DjVu, PDF, EPUB, etc.)
- `--has-ocr` - Only items with OCR text
- `--text` - Search inside book text (full-text search) instead of metadata
- `--include-unavailable` - Include print-disabled and removed items (excluded by default)

#### `info` - Display Metadata

Show metadata about a catalog or IA item:

```bash
# Catalog info
ia-utils info catalog.sqlite

# Remote IA item info
ia-utils info anatomicalatlasi00smit

# Specific fields as JSON
ia-utils info catalog.sqlite -f title -f page_count --output-format json
```

### Catalog Management

#### `create-catalog` - Build Searchable Database

Create a SQLite catalog from any IA document with OCR:

```bash
# Create catalog (auto-generates filename from metadata)
ia-utils create-catalog anatomicalatlasi00smit

# Specify output directory
ia-utils create-catalog anatomicalatlasi00smit -d ./catalogs/

# Custom filename
ia-utils create-catalog anatomicalatlasi00smit -o anatomy.sqlite

# From URL
ia-utils create-catalog https://archive.org/details/anatomicalatlasi00smit

# Use full hOCR mode (slower, includes bounding boxes and confidence)
ia-utils create-catalog anatomicalatlasi00smit --full
```

**Catalog modes** (auto-detected):
- `searchtext` - Fast mode using pre-indexed searchtext (default, text-only)
- `djvu` - Fallback using DjVu XML (includes confidence scores)
- `hocr` - Full mode with bounding boxes, font sizes, confidence (use `--full`)

The catalog includes:
- Document metadata (title, creator, date, subject, etc.)
- Full OCR text organized by page and text block
- FTS5 full-text search indexes
- Page number mappings (leaf to printed page)
- Archive file listings

#### `rebuild-catalog` - Rebuild Indexes

Rebuild FTS indexes or fully regenerate a catalog:

```bash
# Rebuild text blocks and FTS indexes only
ia-utils rebuild-catalog catalog.sqlite

# Full regeneration (re-downloads source files)
ia-utils rebuild-catalog catalog.sqlite --full
```

#### `search-catalog` - Full-Text Search

Search OCR text using SQLite FTS5:

```bash
# Simple search
ia-utils search-catalog -c catalog.sqlite -q "femur"

# Phrase search
ia-utils search-catalog -c catalog.sqlite -q '"circle of willis"'

# Boolean operators
ia-utils search-catalog -c catalog.sqlite -q "anatomy OR physiology"
ia-utils search-catalog -c catalog.sqlite -q "heart NOT surgery"

# Proximity search
ia-utils search-catalog -c catalog.sqlite -q "femur NEAR/5 head"

# Prefix matching
ia-utils search-catalog -c catalog.sqlite -q "anat*"

# Block-level search (more granular)
ia-utils search-catalog -c catalog.sqlite -q "nerve" --blocks

# Export results
ia-utils search-catalog -c catalog.sqlite -q "muscle" --output-format json
```

Hyphenated terms like "self-adjusting" are automatically quoted to prevent FTS5 misinterpretation. Use `--raw` for direct FTS5 control.

### Downloading

#### `get-page` - Download Single Page

```bash
# By leaf number (physical scan order)
ia-utils get-page -c catalog.sqlite -l 42 -o page.jpg

# By printed page number
ia-utils get-page -c catalog.sqlite -b 100 -o page.jpg

# Different sizes: small (~300px), medium (~600px), large (full), original (JP2)
ia-utils get-page -c catalog.sqlite -l 42 --size original -o page.jp2

# Image processing
ia-utils get-page -c catalog.sqlite -l 42 --autocontrast -o page.jpg
ia-utils get-page -c catalog.sqlite -l 42 --cutoff 2 -o page.jpg
```

#### `get-pages` - Download Multiple Pages

```bash
# Download range as individual files
ia-utils get-pages -c catalog.sqlite -l 1-10 -p output/page

# Download as ZIP archive
ia-utils get-pages -c catalog.sqlite -l 100-200 --zip -o chapter.zip

# Download all pages as ZIP
ia-utils get-pages -c catalog.sqlite --all --zip

# With image processing
ia-utils get-pages -c catalog.sqlite -l 1-20 -p pages/scan --autocontrast

# Parallel downloads (default: 4 jobs)
ia-utils get-pages -c catalog.sqlite --all --zip -j 8
```

#### `get-pdf` - Download PDF

```bash
# Download using catalog (uses readable filename)
ia-utils get-pdf -c catalog.sqlite

# Download by identifier
ia-utils get-pdf anatomicalatlasi00smit

# Custom output
ia-utils get-pdf -c catalog.sqlite -o book.pdf -d ./downloads/
```

#### `get-text` - Extract OCR Text

```bash
# Get text for a page
ia-utils get-text -c catalog.sqlite -l 175

# Get text for range
ia-utils get-text -c catalog.sqlite -l 100-110

# Get individual blocks with confidence scores
ia-utils get-text -c catalog.sqlite -l 175 --blocks

# Export as JSON
ia-utils get-text -c catalog.sqlite -l 175 --output-format json
```

#### `get-url` - Get URLs Without Downloading

```bash
# Image URL
ia-utils get-url -c catalog.sqlite -l 42

# Viewer URL
ia-utils get-url -c catalog.sqlite -l 42 --viewer

# PDF URL
ia-utils get-url -c catalog.sqlite --pdf

# PDF URL with page anchor
ia-utils get-url -c catalog.sqlite -l 42 --pdf
```

## Identifiers

Most commands accept Internet Archive identifiers in multiple forms:

```bash
# Plain ID
ia-utils get-pdf anatomicalatlasi00smit

# Full URL
ia-utils get-pdf https://archive.org/details/anatomicalatlasi00smit

# URL with page
ia-utils get-page https://archive.org/details/anatomicalatlasi00smit/page/leaf42/

# From catalog
ia-utils get-pdf -c catalog.sqlite
```

## Output Formats

All commands support multiple output formats via `--output-format`:

| Format | Description |
|--------|-------------|
| `records` | Key-value pairs (default for single results) |
| `table` | Aligned columns (default for multiple results) |
| `json` | JSON array |
| `jsonl` | JSON Lines (one object per line) |
| `csv` | Comma-separated values |

Write to file with `-o`:

```bash
ia-utils search-ia -q "botany" -o results.csv
ia-utils search-catalog -c catalog.sqlite -q "plant" --output-format json -o matches.json
```

## Catalog Database Schema

Catalogs are SQLite databases with these tables:

| Table | Description |
|-------|-------------|
| `document_metadata` | Title, creator, date, subject, etc. |
| `catalog_metadata` | Catalog info: slug, created_at, catalog_mode |
| `text_blocks` | OCR text blocks (hOCR/DjVu modes include bounding boxes, confidence) |
| `pages_fts` | FTS5 index for page-level search |
| `text_blocks_fts` | FTS5 index for block-level search |
| `page_numbers` | Leaf-to-printed-page mapping |
| `archive_files` | Available file formats on IA |

Query directly with sqlite3:

```bash
sqlite3 catalog.sqlite "SELECT page_id, snippet(pages_fts, 0, '>', '<', '...', 20)
    FROM pages_fts WHERE pages_fts MATCH 'anatomy' LIMIT 10"
```

## Verbose Mode

Use `-v` or `--verbose` for detailed progress:

```bash
ia-utils -v create-catalog anatomicalatlasi00smit
ia-utils -v search-ia -q "medical"
```

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=ia_utils
```

## License

MIT
