# Search Reference

Complete reference for searching Internet Archive metadata and catalog content.

## Internet Archive Search (`search-ia`)

### Basic Query Syntax
```bash
# Simple keyword search
ia-utils search-ia -q "anatomy atlas"

# Phrase search
ia-utils search-ia -q '"human anatomy"'

# Field-specific search
ia-utils search-ia -q "title:spalteholz"
ia-utils search-ia -q "creator:Gray"
ia-utils search-ia -q "description:illustrated"
```

### Filtering Options

#### By Date
```bash
--year 1900           # Exact year
--year 1900-1950      # Range (inclusive)
--year 1900-          # After 1900
--year -1950          # Before 1950
```

#### By Creator/Author
```bash
--creator "Gray"
--creator "Spalteholz, Werner"
```

#### By Subject
```bash
--subject "anatomy"
--subject "Human anatomy"
```

#### By Collection
```bash
--collection wellcomelibrary
--collection medicalheritagelibrary
--collection americana
```

Important collections for medical/scientific texts:
- `wellcomelibrary` - Wellcome Library (medical history)
- `medicalheritagelibrary` - Medical Heritage Library consortium
- `medicallibrary` - General medical texts
- `biodiversity` - Biodiversity Heritage Library
- `americana` - American libraries collection

#### By Media Type
```bash
-m texts        # Books and documents (most common)
-m collection   # Collections themselves
-m audio        # Audio recordings
-m movies       # Videos
-m image        # Images
```

#### By Language
```bash
--lang eng      # English
--lang ger      # German
--lang fre      # French
--lang lat      # Latin
```

#### By Format
```bash
-F "hOCR"       # Has hOCR (best for full catalog)
-F "DjVu"       # Has DjVu
-F "PDF"        # Has PDF
-F "EPUB"       # Has EPUB
```

#### OCR Availability
```bash
--has-ocr       # Only items with searchable text
```

### Sorting Results
```bash
-s downloads:desc     # Most downloaded first
-s date:asc          # Oldest first
-s date:desc         # Newest first
-s title:asc         # Alphabetical by title
```

### Output Control

#### Limit and Pagination
```bash
-l 20           # Show 20 results (default)
-l 50           # Show 50 results
-p 2            # Page 2 of results
```

#### Select Fields
```bash
-f identifier -f title -f date    # Specific fields
-f default -f source              # Default + source
-f '*'                            # All fields
```

Default fields: identifier, url, title, creator, date, date_year, mediatype, primary_collection, collection, language, rights, subject, format, downloads, ocr, favorite_collections_count

**Important**: The `rights` field contains copyright and usage information. Always include this when presenting results to users so they can make informed choices about which items to use.

#### Output Format
```bash
--output-format table    # Aligned columns (default for multiple)
--output-format records  # Key-value (default for single)
--output-format json     # JSON array
--output-format jsonl    # JSON Lines
--output-format csv      # CSV
-o results.csv          # Write to file (format auto-detected)
```

### Full-Text Search (Inside Books)
```bash
# Search inside book content, not just metadata
ia-utils search-ia --text "circle of willis" --year 1900-1940 -m texts

# Multiple text terms (AND)
ia-utils search-ia --text "femur" --text "anatomy" -m texts

# Combine metadata search with text search
ia-utils search-ia -q "anatomy atlas" --text "femur" --year 1900-1940 -m texts
```

### Searching for Collections
```bash
# Find collections related to medical libraries
ia-utils search-ia -m collection -q "medical library" -f identifier -f title -f item_count
```

### Examples
```bash
# Anatomy atlases from early 1900s, sorted by popularity
ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts --has-ocr -s downloads:desc

# All works by Spalteholz
ia-utils search-ia --creator "Spalteholz" -m texts --has-ocr

# German medical texts with hOCR
ia-utils search-ia --subject "anatomy" --lang ger -F "hOCR" -m texts

# Export to CSV for analysis
ia-utils search-ia -q "anatomy" --year 1800-1900 -l 100 -o anatomy_books.csv
```

---

## Catalog Search (`search-catalog`)

Search within a local catalog database built from an IA item.

### Basic Syntax
```bash
ia-utils search-catalog -c catalog.sqlite -q "search term"
```

### Query Syntax (FTS5)

#### Simple Terms
```bash
-q "femur"                    # Single term
-q "femur head"               # Both terms (implicit AND)
-q "femur OR tibia"           # Either term
-q "anatomy NOT surgery"      # Exclusion
```

#### Phrases
```bash
-q '"circle of willis"'       # Exact phrase
-q '"inferior extremity"'     # Exact phrase
```

#### Prefix Search
```bash
-q "anat*"                    # Words starting with "anat"
-q "oste*"                    # Words starting with "oste"
```

#### Proximity Search (NEAR)
```bash
-q "femur NEAR head"          # Within 10 words (default)
-q "femur NEAR/5 head"        # Within 5 words
```

#### Hyphenated Terms
By default, hyphenated terms are auto-quoted to prevent FTS5 misinterpretation:
```bash
-q "self-adjusting"           # Searched as literal term
```

Use `--raw` to pass query directly to FTS5:
```bash
-q "self-adjusting" --raw     # Interpreted as "self NOT adjusting"
```

### Output Options

#### Limit Results
```bash
-l 20                         # Default limit
-l 50                         # More results
```

#### Block vs Page Level
```bash
# Page-level search (default) - aggregates blocks per page
ia-utils search-catalog -c catalog.sqlite -q "term"

# Block-level search - finer granularity
ia-utils search-catalog -c catalog.sqlite -q "term" --blocks
```

#### Select Fields
```bash
-f leaf -f page -f snippet -f url    # Default fields
-f leaf -f text                       # Leaf and full text
```

#### Output Format
```bash
--output-format table
--output-format json
--output-format csv
-o results.json
```

### Direct SQL Access

For complex queries, use SQLite directly:

```bash
# Page-level FTS
sqlite3 catalog.sqlite "
SELECT page_id, snippet(pages_fts, 0, '>', '<', '...', 20)
FROM pages_fts
WHERE pages_fts MATCH 'femur NEAR head'
LIMIT 10"

# Block-level FTS
sqlite3 catalog.sqlite "
SELECT page_id, block_number, text
FROM text_blocks tb
JOIN text_blocks_fts fts ON tb.rowid = fts.rowid
WHERE text_blocks_fts MATCH 'femur'
LIMIT 10"

# With page number mapping
sqlite3 catalog.sqlite "
SELECT pn.book_page_number, tb.text
FROM text_blocks tb
JOIN page_numbers pn ON tb.page_id = pn.leaf_num
WHERE tb.text LIKE '%femur%'
LIMIT 10"
```

### Examples
```bash
# Find pages about the femur
ia-utils search-catalog -c catalog.sqlite -q "femur"

# Find exact phrase
ia-utils search-catalog -c catalog.sqlite -q '"circle of willis"'

# Search with exclusion
ia-utils search-catalog -c catalog.sqlite -q "nerve NOT optic"

# Export to JSON
ia-utils search-catalog -c catalog.sqlite -q "anatomy" -o results.json --output-format json

# Block-level search for precise location
ia-utils search-catalog -c catalog.sqlite -q "femur" --blocks -l 20
```

## Search Strategy Tips

### For LLMs Working with Users

1. **Start with metadata search** (`search-ia`) to find the right book
2. **Create catalog** for detailed content search
3. **Use phrase search** for multi-word anatomical terms
4. **Try prefix search** when spelling is uncertain: `oste*` for osteology terms
5. **Use NEAR** for related concepts: `nerve NEAR muscle`
6. **Check the index** - search for "index" and examine those pages directly
7. **Fall back to SQLite** for complex queries or statistics
