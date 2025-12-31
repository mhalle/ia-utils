# Tips and Tricks for LLMs

Advanced techniques and shortcuts for efficiently using ia-utils.

## Engage Users Early - Breadth Over Depth

**Don't drill down making many tool calls trying to find an elusive perfect or comprehensive answer.** Instead, engage users by presenting intermediate results and letting them guide the search.

### Why This Matters

- Users can evaluate sources themselves using BookReader links
- Different users have different needs - let them choose
- Autonomous deep searches waste time if the first result isn't what they wanted
- Showing options teaches users what's available

### The Pattern

1. **Search broadly first** - Run one search, present top results with links
2. **Let users evaluate** - Include BookReader links so they can browse sources
3. **Ask for direction** - "Which of these looks most relevant?" or "Should I search for [alternative term]?"
4. **Drill down on request** - Only go deeper when the user indicates which direction

### Example: Finding Anatomical Information

**❌ Wrong approach** (too many autonomous calls):
```
[Searches for "femur"]
[Creates catalog]
[Searches catalog]
[Downloads 5 pages]
[Reads each page]
[Synthesizes answer]
... 8 tool calls later, presents a comprehensive answer that might not be what the user wanted
```

**✅ Right approach** (engage early):
```
I found several anatomy atlases that might help. Here are the top candidates:

1. [Hand Atlas of Human Anatomy (1933)](https://archive.org/details/b31362138) -
   Spalteholz, 847 pages, high-quality plates. [Browse the atlas](https://archive.org/details/b31362138)

2. [Gray's Anatomy (1918)](https://archive.org/details/anatomyofhumanbo1918gray) -
   Classic reference, 1396 pages. [Browse the book](https://archive.org/details/anatomyofhumanbo1918gray)

3. [Anatomical Atlas (1900)](https://archive.org/details/anatomicalatlasi00smit) -
   Older edition, 500 pages. [Browse the atlas](https://archive.org/details/anatomicalatlasi00smit)

Which would you like me to search? Or browse these links first to see which
has the style of illustrations you prefer.
```

### When to Go Deeper

- User explicitly asks for more detail
- User selects a specific source to explore
- User confirms the search direction is correct
- Simple factual queries with obvious single answers

### Always Include Links

When presenting options, always include BookReader links so users can:
- Evaluate the source's style and quality
- Check if illustrations match their needs
- Browse surrounding content
- Decide if they want to continue with that source

### Link to Specific Pages When Appropriate

Don't just link to the document root - link to specific pages or spreads that are relevant:

```markdown
Found information about the femur in [Gray's Anatomy](https://archive.org/details/anatomyofhumanbo1918gray):

- **Overview**: [page 242](https://archive.org/details/anatomyofhumanbo1918gray/page/leaf242) - general description
- **Articulations**: [page 289](https://archive.org/details/anatomyofhumanbo1918gray/page/leaf289) - joints and connections
- **Muscles**: [page 456](https://archive.org/details/anatomyofhumanbo1918gray/page/leaf456) - attached muscles

Click any link to browse that section and see surrounding content.
```

This helps users:
- Jump directly to relevant content
- Explore related information on adjacent pages
- Compare different sections of the same work

## Quick Decision Tree

```
User wants to find a book?
  └─> search-ia with filters
  └─> Include IA links when presenting results

User has an ID, wants overview?
  └─> info <identifier>
  └─> Link to the item: [Title](https://archive.org/details/<id>)

User wants to search inside a book?
  └─> create-catalog (once), then search-catalog
  └─> Link each result to its page in BookReader

User asks about a specific page?
  └─> get-url --viewer (give them interactive link)

Showing an image to the user?
  └─> get-page, then ALWAYS include BookReader link
  └─> Lets user explore context, zoom, navigate

OCR looks garbled?
  └─> get-page and read the image directly

User needs to compare editions?
  └─> Create catalogs for each, compare search results
  └─> Link each edition so user can explore
```

## Providing Links to Users

**Always include clickable links** when displaying content from IA documents. This lets users verify information, explore context, and navigate the document themselves.

### When to Provide Links

- **First mention of any document**: When introducing a book or document, include a link to the item on Internet Archive
- **Downloaded images**: Always accompany displayed page images with BookReader links so users can explore surrounding context
- Search results: link to each page mentioned
- Quotes or excerpts: link to source page
- Figure/image references: link to viewer page
- Any specific page discussion: include viewer URL

### How to Format Links

```bash
# Get viewer URL (user can navigate, zoom, read)
ia-utils get-url <id> -l <leaf> --viewer
# Returns: https://archive.org/details/<id>/page/leaf<n>

# Get direct image URL
ia-utils get-url <id> -l <leaf>
```

Format as clickable markdown:
```markdown
Found on [page 42](https://archive.org/details/anatomicalatlasi00smit/page/leaf42):
> "The femur articulates with..."

See also: [page 43](https://archive.org/details/anatomicalatlasi00smit/page/leaf43)
```

### Template for Search Results

```markdown
Found 3 matches for "femur":

1. **Page 42** ([view](https://archive.org/details/id/page/leaf42)): "The femur is the longest bone..."
2. **Page 89** ([view](https://archive.org/details/id/page/leaf89)): "...articulation of the femur with..."
3. **Page 156** ([view](https://archive.org/details/id/page/leaf156)): "Figure 23 shows the femur..."
```

### Template for First Document Introduction

When first presenting a document to the user, always include a link:

```markdown
I found a relevant book: [Hand Atlas of Human Anatomy](https://archive.org/details/b31362138)
by Werner Spalteholz (1933). This is a high-quality scan with 800+ pages.

Would you like me to search for specific topics in this atlas?
```

### Template for Displaying Images

When downloading and displaying page images, always include a BookReader link. This lets users explore the surrounding text, zoom, and navigate:

```markdown
Here is the anatomical diagram from page 175:

[Downloaded image displayed here]

[View in BookReader](https://archive.org/details/b31362138/page/leaf175) -
click to explore surrounding pages, zoom, and read related text.
```

For figures specifically:
```markdown
Figure 23 (The Femur) appears on [page 156](https://archive.org/details/b31362138/page/leaf156):

[Downloaded image displayed here]

The BookReader link above lets you see the figure legend and surrounding anatomical descriptions.
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
- [Title (Year)](https://archive.org/details/id1): [downloads] downloads, [ocr]
  Rights: [rights status - e.g., "Public Domain" or "Copyright Not Cleared"]
- [Title (Year)](https://archive.org/details/id2): [downloads] downloads, [ocr]
  Rights: [rights status]

Recommended: [Title](https://archive.org/details/id) because [reason - downloads, OCR quality, completeness, AND clear rights]
```

**Always include rights information** - users need to know about potential restrictions.
**Always link each edition** - users can click to explore before deciding.

### "Find information about X"
```
Searching for [X] in [Book Title](https://archive.org/details/<id>):
[Run search-catalog]

Found on [page 42](https://archive.org/details/<id>/page/leaf42):
> "[snippet]"

[View in BookReader](https://archive.org/details/<id>/page/leaf42) to see full context.

Would you like me to show more context or search for related terms?
```

### "Show me figure Y"
```
[Search for figure reference]
Figure Y appears on [page 89](https://archive.org/details/<id>/page/leaf89).

[Download and display image]

This figure shows [description from viewing image].

[View in BookReader](https://archive.org/details/<id>/page/leaf89) to explore the
figure legend, surrounding text, and related illustrations on adjacent pages.
```
