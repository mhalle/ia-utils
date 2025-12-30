# ia-utils Quick Reference

## Installation
```bash
uv run --with git+https://github.com/mhalle/ia-utils.git ia-utils <command>
```

## Core Workflow
```bash
# 1. Find books
ia-utils search-ia -q "topic" -m texts --has-ocr -s downloads:desc

# 2. Check item info
ia-utils info <identifier>

# 3. Build catalog
ia-utils create-catalog <identifier> -d ./catalogs/

# 4. Search catalog
ia-utils search-catalog -c catalog.sqlite -q "term"

# 5. Get page/URL
ia-utils get-url -c catalog.sqlite -l <leaf> --viewer
ia-utils get-page -c catalog.sqlite -l <leaf> -o page.jpg
```

## Search IA (`search-ia`)
```bash
-q "query"              # Search terms
-m texts                # Media type (texts, collection, audio, movies)
--has-ocr               # Only items with OCR
--year 1900-1950        # Date range
--creator "Name"        # Author
--subject "topic"       # Subject
--collection name       # IA collection
--lang eng              # Language
-s downloads:desc       # Sort by downloads
-s date:asc             # Sort by date
-l 20                   # Limit results
-f field1 -f field2     # Select fields
--text "term"           # Search inside book text (repeatable)
```

## List Files (`list-files`)
```bash
ia-utils list-files <identifier>           # List original files
ia-utils list-files <identifier> --all     # Include derivatives (PDF, OCR, etc.)
ia-utils list-files <identifier> --format-filter PDF
ia-utils list-files <identifier> --format-filter MP3
ia-utils list-files -c catalog.sqlite      # From catalog
-f name -f url                              # Select fields
-o files.csv                                # Export
```

## Search Catalog (`search-catalog`)
```bash
-c catalog.sqlite       # Catalog file (required)
-q "term"               # Search query (required)
-l 20                   # Limit results
--blocks                # Block-level (finer) vs page-level (default)
--raw                   # Pass query directly to FTS5
```

**FTS5 Query Syntax:**
| Pattern | Meaning |
|---------|---------|
| `word` | Contains word |
| `word1 word2` | Both (AND) |
| `word1 OR word2` | Either |
| `"exact phrase"` | Phrase |
| `word*` | Prefix |
| `word1 NEAR word2` | Within 10 words |
| `word1 NEAR/5 word2` | Within 5 words |

## Page Specification
```bash
-l 175                  # Leaf number (physical scan)
-b 145                  # Book page number (printed)
-l 1-10                 # Range
-l 1,5,10               # List
-l 1-5,10,20-25         # Mixed
```

## Get URLs (`get-url`)
```bash
ia-utils get-url -c catalog.sqlite -l 175              # Direct image URL
ia-utils get-url -c catalog.sqlite -l 175 --viewer     # BookReader URL
ia-utils get-url -c catalog.sqlite -l 175 --pdf        # PDF with page anchor
ia-utils get-url -c catalog.sqlite --pdf               # Full PDF URL
--size small|medium|large|original                     # Image size
```

## Get Pages (`get-page`, `get-pages`)
```bash
# Single page
ia-utils get-page -c catalog.sqlite -l 175 -o page.jpg
ia-utils get-page -c catalog.sqlite -b 145 -o page.jpg  # By book page

# Multiple pages
ia-utils get-pages -c catalog.sqlite -l 1-20 -p output/prefix
ia-utils get-pages -c catalog.sqlite -l 1-20 --zip -o pages.zip
ia-utils get-pages -c catalog.sqlite --all --zip

# Options
--size small|medium|large|original
--autocontrast          # Enhance faded scans
```

## Get Text (`get-text`)
```bash
ia-utils get-text -c catalog.sqlite -l 175
ia-utils get-text -c catalog.sqlite -l 100-110
ia-utils get-text -c catalog.sqlite -l 175 --blocks    # Individual blocks
--output-format json|csv|table
```

## Output Formats
```bash
--output-format table   # Columns (default for multiple)
--output-format records # Key-value (default for single)
--output-format json    # JSON array
--output-format jsonl   # JSON Lines
--output-format csv     # CSV
-o filename.csv         # Write to file (format auto-detected)
```

## Page Numbering

| Type | Format | Example | Notes |
|------|--------|---------|-------|
| Leaf | `leaf{n}` | `/page/leaf175` | 0-indexed in URLs |
| Book page | bare number | `/page/145` | OCR-detected, may have errors |
| PDF | `#page=N` | `#page=176` | 1-indexed: PDF page = leaf + 1 |
| n{n} | `n175` | AVOID | Internal BookReader only |

**Conversion:**
```sql
-- Book page → Leaf
SELECT leaf_num FROM page_numbers WHERE book_page_number = '145';

-- Leaf → Book page
SELECT book_page_number FROM page_numbers WHERE leaf_num = 175;
```

## Direct SQL Queries
```bash
# Page-level FTS
sqlite3 catalog.sqlite "SELECT page_id, snippet(pages_fts, 0, '>', '<', '...', 30)
  FROM pages_fts WHERE pages_fts MATCH 'term' LIMIT 10"

# Find unnumbered pages (plates)
sqlite3 catalog.sqlite "SELECT leaf_num FROM page_numbers
  WHERE book_page_number IS NULL ORDER BY leaf_num"

# OCR confidence (hOCR only)
sqlite3 catalog.sqlite "SELECT AVG(avg_confidence) FROM text_blocks"
```

## Key Tables
| Table | Purpose |
|-------|---------|
| `text_blocks` | OCR text by block |
| `page_numbers` | Leaf ↔ book page mapping |
| `pages_fts` | Page-level full-text search |
| `text_blocks_fts` | Block-level full-text search |
| `document_metadata` | IA metadata |
| `catalog_metadata` | Catalog info (mode, date) |

## Rights Check
Always check before recommending:
```bash
ia-utils info <id> -f rights -f possible-copyright-status
```
Safe: "Public Domain", "No Known Copyright", CC licenses, pre-1928 US publications

## Common Patterns

**Find best edition:**
```bash
ia-utils search-ia -q "title" --creator "author" -m texts --has-ocr -s downloads:desc -l 10
```

**Find the index:**
```bash
ia-utils search-catalog -c catalog.sqlite -q "index" -l 5
# Then get text from high leaf numbers
```

**Find a figure:**
```bash
ia-utils search-catalog -c catalog.sqlite -q '"Fig. 123"'
# Download surrounding pages to locate actual image
```

**Check OCR quality quickly:**
```bash
ia-utils search-catalog -c catalog.sqlite -q "common word" -l 3
# If snippets are garbled, OCR is poor
```

## Non-Book Items

Commands `info`, `list-files`, and `search-ia` work with any IA media type:

```bash
# Photos
ia-utils search-ia -q "daguerreotype" -m image
ia-utils list-files photo_id --format-filter JPEG

# Audio
ia-utils search-ia -q "bird songs" -m audio
ia-utils list-files audio_id --format-filter MP3

# Video
ia-utils search-ia -q "silent film" -m movies
ia-utils list-files film_id --format-filter MP4

# Any item metadata
ia-utils info <any_identifier> -f '*'
```

Media types: `texts`, `audio`, `movies`, `image`, `software`, `collection`
