# Database Schema Reference

Indexes are SQLite3 databases. This document describes the schema for each index mode.

## Common Tables (All Modes)

### index_metadata
Stores information about the index itself.

```sql
CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

| Key | Description |
|-----|-------------|
| `slug` | Human-readable filename base |
| `created_at` | Index creation timestamp |
| `index_mode` | `searchtext`, `hocr`, or `djvu` |

### document_metadata
Stores Internet Archive metadata about the document.

```sql
CREATE TABLE document_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

Contains all IA metadata fields: identifier, title, creator, date, description, collection, subject, language, etc.

**Example Query:**
```sql
SELECT key, value FROM document_metadata WHERE key IN ('title', 'creator', 'date');
```

### archive_files
Lists all files available for the IA item.

```sql
CREATE TABLE archive_files (
    filename TEXT PRIMARY KEY,
    format TEXT,
    size_bytes INTEGER,
    source_type TEXT,
    md5_checksum TEXT,
    sha1_checksum TEXT,
    crc32_checksum TEXT,
    download_url TEXT
);
```

**Example Query:**
```sql
-- Find available PDF
SELECT filename, download_url FROM archive_files WHERE format = 'Text PDF';

-- List all formats
SELECT DISTINCT format FROM archive_files;
```

### page_numbers
Maps between physical leaf numbers and printed book page numbers.

```sql
CREATE TABLE page_numbers (
    leaf_num INTEGER PRIMARY KEY,
    book_page_number TEXT,
    confidence INTEGER,
    pageProb INTEGER,
    wordConf INTEGER
);
```

| Column | Description |
|--------|-------------|
| `leaf_num` | Physical scan number (1-indexed in this table, 0-indexed in URLs) |
| `book_page_number` | Printed page (may be NULL, roman numerals, etc.) |
| `confidence` | Overall confidence (0-100) |
| `pageProb` | Page number detection confidence |
| `wordConf` | Word detection confidence |

**Page Numbering Schemes:**
- **leaf_num**: 0-indexed; URLs use `leaf{n}` format (`leaf_num 175` → `/page/leaf175`)
- **book_page_number**: OCR-detected printed page; may have errors, duplicates, or gaps
- **PDF pages**: 1-indexed; **pdf_page = leaf_num + 1** (leaf 175 → PDF page 176)
- **Database note**: `page_numbers.leaf_num` typically starts at 1 (leaf0 may be empty cover)

**WARNING**: Book page numbers are OCR-detected and may be:
- Missing (NULL) for plates, blanks, covers
- Incorrect due to OCR errors
- Duplicated if pages are repeated or misnumbered in the original
- Roman numerals for front matter ("XII", "XIV", etc.)

**Example Queries:**
```sql
-- Look up leaf from book page
SELECT leaf_num FROM page_numbers WHERE book_page_number = '145';

-- Look up book page from leaf
SELECT book_page_number FROM page_numbers WHERE leaf_num = 175;

-- Find roman numeral pages (front matter)
SELECT leaf_num, book_page_number FROM page_numbers
WHERE book_page_number GLOB '*[IVX]*' ORDER BY leaf_num;

-- Find pages without page numbers (plates, illustrations)
SELECT leaf_num FROM page_numbers WHERE book_page_number IS NULL;
```

---

## Searchtext Mode Schema

Default mode - fastest, basic features.

### text_blocks
```sql
CREATE TABLE text_blocks (
    page_id INTEGER,
    block_number INTEGER,
    text TEXT,
    length INTEGER,
    PRIMARY KEY (page_id, block_number)
);
```

| Column | Description |
|--------|-------------|
| `page_id` | Leaf number (same as `leaf_num` in page_numbers) |
| `block_number` | Block sequence within page (0-indexed) |
| `text` | OCR text content |
| `length` | Character count |

### pages
Byte offsets for efficient text retrieval.

```sql
CREATE TABLE pages (
    page_id INTEGER PRIMARY KEY,
    char_start INTEGER,
    char_end INTEGER,
    hocr_byte_start INTEGER,
    hocr_byte_end INTEGER
);
```

### FTS Tables

**Page-level FTS** (aggregated text per page):
```sql
CREATE VIRTUAL TABLE pages_fts USING fts5(
    page_text,
    page_id UNINDEXED
);
```

**Block-level FTS**:
```sql
CREATE VIRTUAL TABLE text_blocks_fts USING FTS5 (
    text,
    content=text_blocks
);
```

**Example FTS Queries:**
```sql
-- Page-level search
SELECT page_id, snippet(pages_fts, 0, '→', '←', '...', 30)
FROM pages_fts
WHERE pages_fts MATCH 'femur'
ORDER BY rank
LIMIT 10;

-- Block-level search
SELECT tb.page_id, tb.block_number, snippet(text_blocks_fts, 0, '→', '←', '...', 20) as snippet
FROM text_blocks_fts fts
JOIN text_blocks tb ON fts.rowid = tb.rowid
WHERE text_blocks_fts MATCH 'femur NEAR head'
LIMIT 10;

-- Search with page number mapping
SELECT pn.book_page_number, snippet(pages_fts, 0, '→', '←', '...', 30)
FROM pages_fts pf
JOIN page_numbers pn ON pf.page_id = pn.leaf_num
WHERE pages_fts MATCH '"circle of willis"';
```

---

## hOCR Mode Schema (--full)

Full mode with bounding boxes and confidence scores.

### text_blocks (hOCR)
```sql
CREATE TABLE text_blocks (
    page_id INTEGER,
    block_number INTEGER,
    hocr_id TEXT PRIMARY KEY,
    block_type TEXT,
    language TEXT,
    text_direction TEXT,
    bbox_x0 INTEGER,
    bbox_y0 INTEGER,
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    text TEXT,
    line_count INTEGER,
    length INTEGER,
    avg_confidence FLOAT,
    avg_font_size INTEGER,
    parent_carea_id TEXT
);
```

| Column | Description |
|--------|-------------|
| `hocr_id` | hOCR element ID |
| `block_type` | Usually `ocr_par` (paragraph) |
| `language` | Detected language |
| `text_direction` | Text direction (ltr, rtl) |
| `bbox_*` | Bounding box coordinates |
| `avg_confidence` | OCR confidence (0-100) |
| `avg_font_size` | Detected font size |
| `parent_carea_id` | Parent content area |

**Additional Indexes:**
```sql
CREATE INDEX idx_block_type ON text_blocks(block_type);
CREATE INDEX idx_language ON text_blocks(language);
CREATE INDEX idx_confidence ON text_blocks(avg_confidence);
CREATE INDEX idx_font_size ON text_blocks(avg_font_size);
```

**Example hOCR Queries:**
```sql
-- Find high-confidence blocks
SELECT page_id, substr(text, 1, 50), avg_confidence
FROM text_blocks
WHERE avg_confidence > 80
ORDER BY avg_confidence DESC
LIMIT 20;

-- OCR quality statistics
SELECT
    AVG(avg_confidence) as avg,
    MIN(avg_confidence) as min,
    MAX(avg_confidence) as max
FROM text_blocks
WHERE avg_confidence IS NOT NULL;

-- Find blocks by position (e.g., headers at top of page)
SELECT page_id, text, bbox_y0
FROM text_blocks
WHERE bbox_y0 < 200
ORDER BY page_id, bbox_y0;

-- Find large text (titles, headers)
SELECT page_id, text, avg_font_size
FROM text_blocks
WHERE avg_font_size > 20
ORDER BY avg_font_size DESC;
```

---

## Useful Query Patterns

### Get Full Page Text
```sql
SELECT group_concat(text, ' ') as full_text
FROM text_blocks
WHERE page_id = 175
ORDER BY block_number;
```

### Count Pages and Blocks
```sql
SELECT COUNT(*) as total_blocks FROM text_blocks;
SELECT COUNT(DISTINCT page_id) as total_pages FROM text_blocks;
```

### Find Duplicate Content
```sql
SELECT text, COUNT(*) as occurrences
FROM text_blocks
WHERE length > 20
GROUP BY text
HAVING COUNT(*) > 1
ORDER BY occurrences DESC
LIMIT 20;
```

### Export Page Range as Text
```sql
SELECT page_id, group_concat(text, ' ')
FROM text_blocks
WHERE page_id BETWEEN 100 AND 110
GROUP BY page_id
ORDER BY page_id;
```

### Join with Page Numbers
```sql
SELECT
    pn.book_page_number,
    pn.leaf_num,
    group_concat(tb.text, ' ') as text
FROM page_numbers pn
JOIN text_blocks tb ON pn.leaf_num = tb.page_id
WHERE pn.book_page_number IN ('145', '146', '147')
GROUP BY pn.leaf_num
ORDER BY pn.leaf_num;
```

### FTS5 Syntax Reference

| Pattern | Meaning |
|---------|---------|
| `word` | Contains word |
| `word1 word2` | Contains both (AND) |
| `word1 OR word2` | Contains either |
| `word1 NOT word2` | Contains first but not second |
| `"exact phrase"` | Exact phrase match |
| `word*` | Prefix match |
| `word1 NEAR word2` | Within 10 words |
| `word1 NEAR/5 word2` | Within 5 words |
| `^word` | At beginning of field |

---

## Tips for LLMs

1. **Use page_numbers for navigation**: Always join with this table when presenting results to users
2. **Check confidence in hOCR**: Low confidence blocks may have OCR errors
3. **Aggregate at page level**: For most searches, page-level results are more useful
4. **Use FTS for speed**: Direct LIKE queries are slow; FTS is optimized
5. **Watch for NULL page numbers**: These are often plates, illustrations, or blank pages
