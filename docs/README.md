# ia-utils: Internet Archive Book Tools

A command-line tool for discovering, cataloging, and extracting content from Internet Archive books and documents. This guide is designed for LLMs and humans working together to explore historical texts.

## Quick Install

```bash
# Run directly without installation using uv
uv run --with git+https://github.com/mhalle/ia-utils.git ia-utils --help
```

## Documentation Index

### Core Reference
- **[Quick Reference](quick-reference.md)** - Single-page command cheatsheet
- **[Workflow Guide](workflow-guide.md)** - Step-by-step workflows for common tasks
- **[Search Reference](search-reference.md)** - Detailed search options and examples
- **[Catalog Reference](catalog-reference.md)** - Building and querying catalogs

### Advanced Topics
- **[Page Navigation](page-navigation.md)** - Working with pages, leafs, figures, and plates
- **[Database Schema](database-schema.md)** - SQLite schema details for direct queries
- **[Collections](collections.md)** - Guide to IA collections by subject area
- **[Multi-Volume Works](multi-volume.md)** - Handling books split across multiple items

### For LLMs
- **[Tips and Tricks](tips-and-tricks.md)** - Advanced techniques and patterns
- **[Troubleshooting](troubleshooting.md)** - Common problems and solutions
- **[Example Session](example-session.md)** - Complete walkthrough with worked examples

## Core Concepts

### Identifiers
Every Internet Archive item has a unique identifier:
- **ID**: `b31362138`, `cunninghamstextb00cunn`
- **URL**: `https://archive.org/details/b31362138`
- Items can also be referenced via a local catalog: `-c catalog.sqlite`

### Leaf vs Book Page
- **Leaf**: Physical scan number, sequential with no gaps
  - In URLs: `leaf{n}` format: `page/leaf0`, `page/leaf175`
  - In commands: `-l 175` produces `/page/leaf175` (pass-through)
- **Book Page**: Printed page number recognized by OCR
  - May include roman numerals ("XII"), have duplicates, omissions, or OCR errors
  - Used in IA BookReader as bare numbers: `page/145`
- **PDF Page**: 1-indexed; `book.pdf#page=N` where N = leaf + 1 (leaf 175 → page 176)
- **n{n} format**: Internal BookReader format - DO NOT use in output (unreliable outside BookReader)
- The `page_numbers` table maps between leaf and book page numbers

### Copyright and Rights
Always check the `rights` field in document metadata before recommending items:
- Some items have clear public domain status
- Others may have copyright restrictions or unclear status
- Include rights information when presenting search results to users

### Catalog Modes
When building a catalog, three modes are available:
| Mode | Flag | Speed | Features |
|------|------|-------|----------|
| searchtext | (default) | Fast | Basic text, page-level search |
| djvu | (fallback) | Medium | Confidence scores |
| hocr | `--full` | Slow | Bounding boxes, font sizes, confidence |

## Typical Workflow

```bash
# 1. DISCOVER: Find books on Internet Archive
ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts --has-ocr

# 2. INSPECT: Get metadata about a specific item
ia-utils info b31362138

# 3. CREATE CATALOG: Build searchable database
ia-utils create-catalog b31362138 -d ./catalogs/

# 4. SEARCH: Find pages by content
ia-utils search-catalog -c catalog.sqlite -q "femur"

# 5. VIEW: Get page images or URLs
ia-utils get-page -c catalog.sqlite -l 175
ia-utils get-url -c catalog.sqlite -l 175 --viewer
```

## Command Summary

| Command | Purpose |
|---------|---------|
| `search-ia` | Search IA metadata and full text |
| `info` | Show metadata for item or catalog |
| `create-catalog` | Build SQLite catalog from IA item |
| `search-catalog` | Full-text search within catalog |
| `get-page` | Download page image |
| `get-pages` | Download multiple pages (or ZIP) |
| `get-url` | Get URL for page, viewer, or PDF |
| `get-text` | Extract OCR text from catalog |
| `get-pdf` | Download PDF |
| `rebuild-catalog` | Rebuild FTS indexes |

## Key Options Reference

### Search Filters (`search-ia`)
```bash
--year 1900-1940        # Date range
--creator "Spalteholz"  # Author name
--subject "anatomy"     # Subject
--collection wellcome   # IA collection
--has-ocr              # Only items with OCR
-s downloads:desc      # Sort by popularity
--text                 # Search inside book text (not just metadata)
```

### Output Formats
```bash
--output-format table   # Aligned columns (default)
--output-format json    # JSON array
--output-format jsonl   # JSON Lines
--output-format csv     # CSV
--output-format records # Key-value pairs
```

### Page Specification
```bash
-l 175          # Leaf number (physical scan)
-b 145          # Book page number (printed)
-l 1-10         # Range
-l 1,5,10       # List
-l 1-5,10,20-25 # Mixed
```

## Example Session

```bash
# Find anatomy atlases from 1900-1940, sorted by downloads
$ ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts --has-ocr -s downloads:desc -l 5

# Create catalog for Spalteholz atlas
$ ia-utils create-catalog b31362138 -d ./catalogs/

# Search for "femur" in the catalog
$ ia-utils search-catalog -c catalogs/spalteholz*.sqlite -q "femur"
leaf: 175
page: 145
snippet: ...Right thigh bone, →femur←, inferior extremity...
url: https://archive.org/details/b31362138/page/leaf175

# Get the viewer URL for that page
$ ia-utils get-url -c catalogs/spalteholz*.sqlite -l 175 --viewer
https://archive.org/details/b31362138/page/leaf175

# Download the page image
$ ia-utils get-page -c catalogs/spalteholz*.sqlite -l 175 -o femur-page.jpg
```

## For LLMs: Quick Decision Guide

1. **User wants to find a book** → Use `search-ia` with appropriate filters
2. **User has an IA ID and wants details** → Use `info <identifier>`
3. **User wants to search inside a book** → First `create-catalog`, then `search-catalog`
4. **User asks about a specific page** → Use `get-url --viewer` to give them a link
5. **User needs to see a figure** → Use `get-page` to download and display it
6. **OCR quality is poor** → Download page image with `get-page` and read it visually
7. **User needs page number mapping** → Query `page_numbers` table directly

See the detailed guides linked above for comprehensive information.
