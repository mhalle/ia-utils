# Tips and Tricks for LLMs

Advanced techniques and shortcuts for efficiently using ia-utils.

## Quick Decision Tree

```
User wants to find a book?
  └─> search-ia with filters

User has an ID, wants overview?
  └─> info <identifier>

User wants to search inside a book?
  └─> create-catalog (once), then search-catalog

User asks about a specific page?
  └─> get-url --viewer (give them interactive link)

OCR looks garbled?
  └─> get-page and read the image directly

User needs to compare editions?
  └─> Create catalogs for each, compare search results
```

## Efficiency Tips

### 1. Cache Catalog Location
After creating a catalog, note its path. The default naming convention is:
```
{creator}-{title}-{year}_{ia_id}.sqlite
```
Example: `spalteholz-hand-atlas-human-anatomy-1933_b31362138.sqlite`

### 2. Use Glob Patterns for Catalogs
```bash
ia-utils search-catalog -c catalogs/spalteholz*.sqlite -q "femur"
```

### 3. Skip Full Mode Unless Needed
Default `create-catalog` is usually sufficient. Only use `--full` when you need:
- OCR confidence scores
- Bounding box coordinates
- Font size information

### 4. Viewer URLs are Best for Users
Always prefer `--viewer` when giving links to users:
```bash
ia-utils get-url -c catalog.sqlite -l 175 --viewer
# Better: https://archive.org/details/b31362138/page/leaf175
# (user can navigate, zoom, read)
```

### 5. Download Images for Figures
When discussing figures or diagrams, download and display them:
```bash
ia-utils get-page -c catalog.sqlite -l 175 -o fig.jpg
```

## Handling OCR Quality Issues

### Symptoms of Poor OCR
- Garbled snippets in search results
- Missing expected search terms
- Low confidence scores (in hOCR mode)

### Solutions

**1. Visual Inspection**
```bash
ia-utils get-page -c catalog.sqlite -l <problem_leaf> -o check.jpg
# Then read the image directly
```

**2. Check Confidence (hOCR only)**
```sql
SELECT AVG(avg_confidence), MIN(avg_confidence)
FROM text_blocks
WHERE page_id = <leaf>;
```

**3. Try Different Search Terms**
Old texts often have archaic spellings or OCR substitutions:
- `s` ↔ `f` (long s in old texts)
- `ii` ↔ `n`
- `rn` ↔ `m`

**4. Use Prefix Search**
```bash
ia-utils search-catalog -c catalog.sqlite -q "anat*"
```

## Finding Book Structure

### Identify Front Matter
```sql
SELECT leaf_num, book_page_number
FROM page_numbers
WHERE leaf_num < 50
ORDER BY leaf_num;
```
Look for: cover, title, preface (roman numerals), TOC

### Identify Back Matter
```sql
SELECT leaf_num, book_page_number
FROM page_numbers
WHERE leaf_num > (SELECT MAX(leaf_num) - 100 FROM page_numbers)
ORDER BY leaf_num;
```
Look for: appendix, index, plates

### Find Chapter Boundaries
Search for chapter markers:
```bash
ia-utils search-catalog -c catalog.sqlite -q "CHAPTER"
ia-utils search-catalog -c catalog.sqlite -q "PART"
ia-utils search-catalog -c catalog.sqlite -q "SECTION"
```

## Advanced Search Techniques

### Combine FTS with SQL Filters
```sql
-- Find high-confidence blocks mentioning femur
SELECT tb.page_id, tb.text, tb.avg_confidence
FROM text_blocks tb
JOIN text_blocks_fts fts ON tb.rowid = fts.rowid
WHERE text_blocks_fts MATCH 'femur'
AND tb.avg_confidence > 70;
```

### Search with Page Number Context
```sql
SELECT pn.book_page_number, snippet(pages_fts, 0, '→', '←', '...', 30)
FROM pages_fts pf
JOIN page_numbers pn ON pf.page_id = pn.leaf_num
WHERE pages_fts MATCH 'nerve'
AND pn.book_page_number IS NOT NULL
ORDER BY CAST(pn.book_page_number AS INTEGER);
```

### Find Content Near Index
```sql
-- Get index page numbers first
SELECT leaf_num FROM page_numbers
WHERE book_page_number GLOB '[0-9]*'
ORDER BY CAST(book_page_number AS INTEGER) DESC
LIMIT 5;

-- Then search within those pages
SELECT * FROM pages_fts
WHERE page_id > 900  -- Adjust based on book
AND pages_fts MATCH 'term';
```

## Working with Multiple Books

### Compare Same Topic Across Books
```bash
# Create catalogs for comparison candidates
for id in book1 book2 book3; do
  ia-utils create-catalog $id -d ./compare/
done

# Search each
for f in ./compare/*.sqlite; do
  echo "=== $(basename $f) ==="
  ia-utils search-catalog -c "$f" -q "topic" -l 5
done
```

### Build a Corpus Database
For research across many books, create a master index:
```sql
-- In a new database
CREATE TABLE corpus (
  source_catalog TEXT,
  ia_id TEXT,
  leaf INTEGER,
  book_page TEXT,
  text TEXT
);

-- Populate from each catalog
INSERT INTO corpus
SELECT 'catalog1.sqlite', 'id1', page_id, pn.book_page_number, text
FROM text_blocks tb
LEFT JOIN page_numbers pn ON tb.page_id = pn.leaf_num;
```

## Common Pitfalls

### 1. Confusing Leaf and Book Page
- Search results show LEAF numbers (physical scan order)
- Users usually think in BOOK PAGE numbers (printed pages)
- Always clarify or convert using the `page_numbers` table
- ia-utils `-l 175` produces `/page/leaf175` directly

### 2. Using Wrong URL Format
- **ALWAYS use `leaf{n}` format** for URLs: `/page/leaf175`
- **NEVER use `n{n}` format**: `/page/n175` is internal to BookReader and unreliable
- Book page URLs work: `/page/145` but may have OCR issues (wrong number detected)
- PDF pages are 1-indexed: leaf 175 → `#page=176` (pdf_page = leaf + 1)

### 3. Assuming OCR is Perfect
- Old texts often have OCR errors
- Verify critical passages visually
- Use fuzzy matching when possible
- Book page numbers can be wrong, duplicated, or missing

### 4. Missing the Index
- Many questions can be answered from the book's index
- Index pages are usually at high leaf numbers
- Get index text and search it

### 5. Ignoring Roman Numerals
- Front matter uses roman numerals
- `page_numbers` stores them as text ("XII")
- Use pattern matching:
```sql
WHERE book_page_number GLOB '*[IVXLCDM]*'
```

### 6. Not Checking Rights
- Some items have copyright restrictions
- **Always include rights info** when presenting search results
- Check multiple fields in metadata:
  - `rights` - primary rights/copyright statement
  - `possible-copyright-status` - additional copyright assessment
  - `licenseurl` - link to specific license (e.g., Creative Commons)
  - `access-restricted-item` - whether access is restricted
- Quick check: `ia-utils info <id> -f rights -f possible-copyright-status -f licenseurl`
- Common values:
  - "Public Domain" - safe to use
  - "Copyright Not Cleared" - may have restrictions
  - Rights URLs (rightsstatements.org) - check the link
- Wellcome Library items often have clearest rights statements

## Shortcuts

### Quick Metadata Check
```bash
ia-utils info <id> -f title -f date -f ocr -f downloads
```

### Quick Quality Check
```bash
ia-utils create-catalog <id> -d /tmp/
ia-utils search-catalog -c /tmp/*.sqlite -q "common word" -l 3
rm /tmp/*.sqlite  # Clean up
```

### Quick Page Preview
```bash
ia-utils get-url <id> -l 50 --viewer
# Opens middle-ish page in viewer
```

### Get Just the PDF
```bash
ia-utils get-pdf <id>
# Downloads as <id>.pdf
```

## Template Responses for Users

### "What editions are available?"
```
I'll search for editions of [work]:
[Run search-ia with author/title]

Key factors to consider:
- [id1]: [year], [downloads] downloads, [ocr]
  Rights: [rights status - e.g., "Public Domain" or "Copyright Not Cleared"]
- [id2]: [year], [downloads] downloads, [ocr]
  Rights: [rights status]

Recommended: [id] because [reason - downloads, OCR quality, completeness, AND clear rights]
```

**Always include rights information** - users need to know about potential restrictions.

### "Find information about X"
```
Searching for [X] in [book title]:
[Run search-catalog]

Found on page [book_page] (leaf [leaf]):
[snippet]

Would you like to:
1. See the full page text
2. View the page in the IA reader
3. Download the page image
```

### "Show me figure Y"
```
[Search for figure reference]
Figure Y appears on page [page] (leaf [leaf]).

[Download and display image]

This figure shows [description from viewing image].
```
