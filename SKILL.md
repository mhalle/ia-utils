---
name: ia-utils
description: Work with Internet Archive books and documents. Use when searching IA metadata, creating searchable indexes from OCR text, downloading pages, PDFs, or getting URLs, or querying local indexes. Triggers on "Internet Archive", "archive.org", "IA document", "OCR index", or historical book/document research.
license: MIT
compatibility: Requires uv and Python 3.9+. Requires network access to archive.org. The ocr-page command requires the tesseract or tesseract-ocr package to be installed in the OS.
metadata:
  author: mhalle
  repository: https://github.com/mhalle/ia-utils
  download: https://github.com/mhalle/ia-utils/releases/latest/download/ia-utils.zip
---

# ia-utils: Internet Archive Document Tools

CLI tools for discovering, indexing, and downloading books and documents from the Internet Archive.

## Download

Latest release:
- https://github.com/mhalle/ia-utils/releases/latest/download/ia-utils.zip
- https://github.com/mhalle/ia-utils/releases/latest/download/ia-utils.skill

## Installation

Run the install script:

```bash
sh $SKILL_DIR/scripts/install.sh
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
sh $SKILL_DIR/scripts/install.sh --force
```

Note: `$SKILL_DIR` refers to the skill directory path (e.g., `/mnt/skills/ia-utils` depending on platform).

## Quick Start

```bash
# Search Internet Archive
ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts

# Create searchable index from a document
ia-utils create-index <ia_id> -d ./indexes/

# Search index by OCR text
ia-utils search-index -i index.sqlite -q "femur"

# Download a page
ia-utils get-page -i index.sqlite -l 42 -o page.jpg
```

## Commands

**Discovery:**
- `search-ia` - Search IA metadata (title, creator, year, collection)
- `info` - Show metadata for index or IA item
- `list-files` - List files in IA item with download URLs

**Index:**
- `create-index` - Build SQLite database from IA document OCR
- `search-index` - Full-text search index OCR content

**Download:**
- `get-page` - Download single page image
- `get-pages` - Download multiple pages (range or all)
- `get-pages --mosaic` - Create visual overview grid of pages (for LLM vision)
- `get-pdf` - Download PDF from IA
- `get-url` - Get URL without downloading
- `ocr-page` - Run local OCR on a page (requires tesseract)

## Documentation

See [references/REFERENCE.md](references/REFERENCE.md) for complete documentation including:

- Command cheatsheets and workflow guides
- Search syntax and index building
- Database schema for direct SQL queries
- Troubleshooting and tips

## Key Concepts

### Identifiers
Commands accept IA identifiers in multiple forms:
- ID: `anatomicalatlasi00smit`
- URL: `https://archive.org/details/anatomicalatlasi00smit`
- Index: `-i index.sqlite` (reads ID from database)

### Leaf vs Book Page Numbers
- **Leaf** (`-l`): Physical scan index (0-based), maps directly to image files
- **Book** (`-b`): Printed page number, requires lookup in index

### Index Modes
- **searchtext**: Fast, uses pre-indexed text (default)
- **djvu**: Fallback, includes confidence scores
- **hocr**: Full mode with bounding boxes (`--full` flag)

## Common Workflows

### Discovering Resources
Use multiple approaches to find relevant books, documents, images, and other resources:

1. **General knowledge**: Use what you know about the topic - key authors, landmark publications, historical periods, and related subjects
2. **Web search of archive.org**: Search the web for `site:archive.org <topic>` to find items, collections, and curated lists
3. **ia-utils search-ia**: Search IA metadata directly for precise filtering by year, mediatype, collection, and OCR availability

Combine these approaches: start with general knowledge to identify search terms, use web search to discover collections and notable items, then use `search-ia` to systematically explore with filters.

### Find and Download a Historical Book
```bash
# 1. Search for books
ia-utils search-ia -q "Gray's Anatomy" --year 1900-1920 -m texts --has-ocr

# 2. Check item details and rights
ia-utils info <id> -f title -f date -f rights -f imagecount

# 3. Create index for searching
ia-utils create-index <id> -d ./indexes/

# 4. Search for specific content
ia-utils search-index -i index.sqlite -q "femur"

# 5. Download relevant pages
ia-utils get-page -i index.sqlite -l 42 -o femur.jpg
```

### Rights Check
Always verify rights before recommending items:
```bash
ia-utils info <id> -f rights -f possible-copyright-status -f licenseurl
```
Safe values: "Public Domain", "No Known Copyright", CC licenses, pre-1928 US publications.

### Visual Exploration with Mosaic
Use `--mosaic` to create a grid of page thumbnails for quick visual scanning. This is ideal for understanding book structure, finding illustrations, covers, TOC, indexes, or blank pages.

```bash
# Quick overview: every 10th page of entire book
ia-utils get-pages -i index.sqlite -l :10 --mosaic -o overview.jpg

# Sample first 100 pages, every 5th
ia-utils get-pages <id> -l 0-100:5 --mosaic -o sample.jpg

# Dense scan with more columns
ia-utils get-pages -i index.sqlite -l :5 --mosaic --cols 15 -o dense.jpg

# Show book page numbers instead of leaf numbers
ia-utils get-pages -i index.sqlite -b 1-100 --mosaic --label book -o pages.jpg
```

Range syntax with step: `1-100:10` = every 10th (1,11,21...), `:10` = every 10th from start to end.

Mosaic options: `--width` (default 1536), `--cols` (default 12), `--label` (leaf/book/none), `--grid`.

Use `--cols` to balance page count vs resolution: fewer columns = larger tiles with more detail, more columns = fit more pages. Image quality auto-scales with tile size (small/medium/large).

## Tips

- **Engage users with intermediate results**: Don't drill down making many tool calls trying to find a perfect or comprehensive answer. Instead:
  - Present intermediate results early (breadth over depth)
  - Include BookReader links to specific pages so users can evaluate sources themselves
  - Ask for preferences and present options for continuing the search
  - Let the user guide which direction to explore further
- **Always provide clickable links**: When displaying content to users, include viewer URLs so they can explore the document themselves:
  ```bash
  ia-utils get-url <id> -l <leaf> --viewer  # BookReader link
  ia-utils get-url <id> -l <leaf>           # Direct image link
  ```
  Format as clickable markdown links: `[View page 42](https://archive.org/details/id/page/leaf42)`
- **Link documents when first presented**: When introducing a book or document to the user for the first time, always include a link to the item on Internet Archive: `[Title](https://archive.org/details/<id>)`
- **Link images to their context**: When downloading and displaying page images to the user, always accompany them with a BookReader link to that page. This allows users to explore surrounding text and images: `[View in context](https://archive.org/details/<id>/page/leaf<n>)`
- **Use mosaic for visual understanding**: Before diving into specific pages, create a mosaic overview (`get-pages --mosaic -l :10`) to understand the book's structure - where illustrations are, chapter breaks, front/back matter, etc. This helps identify relevant sections quickly.
- Use `--has-ocr` when searching to ensure text is available
- Wellcome Library (`-c wellcomelibrary`) has high-quality medical scans
- Google Books scans are older with lower resolution
- Use `-f '*'` to see all available metadata fields
- For complex index queries, use `sqlite3` directly on the .sqlite file
