---
name: ia-utils
description: Work with Internet Archive books and documents. Use when searching IA metadata, creating searchable catalogs from OCR text, downloading pages or PDFs, or querying local catalogs. Triggers on "Internet Archive", "archive.org", "IA document", "OCR catalog", or historical book/document research.
license: MIT
compatibility: Requires uv and Python 3.9+. Requires network access to archive.org.
metadata:
  author: mhalle
  repository: https://github.com/mhalle/ia-utils
---

# ia-utils: Internet Archive Document Tools

CLI tools for discovering, cataloging, and downloading books and documents from the Internet Archive.

## Installation

Run the install script:

```bash
$SKILL_DIR/scripts/install.sh
```

Or install manually with uv (recommended) or pip:

```bash
uv tool install $SKILL_DIR
# or
pip install $SKILL_DIR
```

Then run from any directory:

```bash
ia-utils <command> [options]
```

To reinstall/upgrade:

```bash
$SKILL_DIR/scripts/install.sh --force
```

Note: `$SKILL_DIR` refers to the skill directory path (e.g., `/mnt/skills/ia-utils` depending on platform).

## Quick Start

```bash
# Search Internet Archive
ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts

# Create searchable catalog from a document
ia-utils create-catalog <ia_id> -d ./catalogs/

# Search catalog by OCR text
ia-utils search-catalog -c catalog.sqlite -q "femur"

# Download a page
ia-utils get-page -c catalog.sqlite -l 42 -o page.jpg
```

## Command Overview

| Command | Purpose |
|---------|---------|
| `search-ia` | Search IA metadata (title, creator, year, collection) |
| `info` | Show metadata for catalog or IA item |
| `create-catalog` | Build SQLite database from IA document OCR |
| `search-catalog` | Full-text search catalog OCR content |
| `get-page` | Download single page image |
| `get-pages` | Download multiple pages (range or all) |
| `get-pdf` | Download PDF from IA |
| `get-url` | Get URL without downloading |

## Documentation

See [references/REFERENCE.md](references/REFERENCE.md) for complete documentation including:

- Command cheatsheets and workflow guides
- Search syntax and catalog building
- Database schema for direct SQL queries
- Troubleshooting and tips

## Key Concepts

### Identifiers
Commands accept IA identifiers in multiple forms:
- ID: `anatomicalatlasi00smit`
- URL: `https://archive.org/details/anatomicalatlasi00smit`
- Catalog: `-c catalog.sqlite` (reads ID from database)

### Leaf vs Book Page Numbers
- **Leaf** (`-l`): Physical scan index (0-based), maps directly to image files
- **Book** (`-b`): Printed page number, requires lookup in catalog

### Catalog Modes
- **searchtext**: Fast, uses pre-indexed text (default)
- **djvu**: Fallback, includes confidence scores
- **hocr**: Full mode with bounding boxes (`--full` flag)

## Common Workflows

### Find and Download a Historical Book
```bash
# 1. Search for books
ia-utils search-ia -q "Gray's Anatomy" --year 1900-1920 -m texts --has-ocr

# 2. Check item details and rights
ia-utils info <id> -f title -f date -f rights -f imagecount

# 3. Create catalog for searching
ia-utils create-catalog <id> -d ./catalogs/

# 4. Search for specific content
ia-utils search-catalog -c catalog.sqlite -q "femur"

# 5. Download relevant pages
ia-utils get-page -c catalog.sqlite -l 42 -o femur.jpg
```

### Rights Check
Always verify rights before recommending items:
```bash
ia-utils info <id> -f rights -f possible-copyright-status -f licenseurl
```
Safe values: "Public Domain", "No Known Copyright", CC licenses, pre-1928 US publications.

## Tips

- Use `--has-ocr` when searching to ensure text is available
- Wellcome Library (`-c wellcomelibrary`) has high-quality medical scans
- Google Books scans are older with lower resolution
- Use `-f '*'` to see all available metadata fields
- For complex catalog queries, use `sqlite3` directly on the .sqlite file
