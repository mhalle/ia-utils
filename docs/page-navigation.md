# Page Navigation Reference

This guide covers navigating between pages, leafs, figures, and references in Internet Archive books.

## Understanding Page Numbering Schemes

Internet Archive uses several page numbering schemes. Understanding them is critical for accurate navigation.

### Leaf Number
- **Definition**: Physical scan order (image file number)
- **Range**: 0 to imagecount-1 (leaf0 is typically cover or first scan)
- **URL format**: `leaf{n}`: `page/leaf0`, `page/leaf175`
- **ia-utils commands**: Pass the leaf number directly with `-l` (e.g., `-l 175` → `/page/leaf175`)
- **File names**: `book_0175.jp2` (0-padded, matches leaf number)
- **Always sequential**: No gaps, includes all scans (cover, blanks, plates, everything)
- **Database**: `page_numbers.leaf_num` typically starts at 1 (first page with content)

### Book Page Number
- **Definition**: Printed page number visible on the page, recognized by OCR
- **Format**: Numbers ("145"), roman numerals ("XII"), or NULL/empty
- **URL format**: Bare number in BookReader: `page/145`
- **Potential issues**:
  - OCR errors (misread numbers)
  - Duplicates (same number on multiple pages)
  - Omissions (unnumbered plates, blanks)
  - Gaps (missing pages in original)
- **Usage**: Referenced in book indexes and tables of contents

### PDF Page Number
- **Definition**: Page number within the PDF file
- **Range**: 1-indexed; **pdf_page = leaf + 1**
- **URL format**: `book.pdf#page=N`
- **Example**: leaf 175 → `book.pdf#page=176`

### n{n} Format (AVOID)
- **Definition**: Internal BookReader numbering scheme
- **Format**: `n0`, `n1`, `n175`
- **WARNING**: Do not use this format in output - it's problematic outside the BookReader interface and may not resolve correctly in other contexts

### The page_numbers Table
```
leaf_num | book_page_number | confidence
---------|------------------|------------
1        | NULL            |            (cover)
2        | NULL            |            (title page)
12       | VIII            | 100        (preface)
30       | 1               | 100        (chapter start)
175      | 145             | 100        (body text)
```

## Converting Between Page and Leaf

### Command Line
```bash
# Get URL for book page 145 (auto-converts to leaf)
ia-utils get-url -c catalog.sqlite -b 145

# Get URL for leaf 175
ia-utils get-url -c catalog.sqlite -l 175
```

### SQL Queries
```sql
-- Book page to leaf
SELECT leaf_num FROM page_numbers WHERE book_page_number = '145';
-- Returns: 175

-- Leaf to book page
SELECT book_page_number FROM page_numbers WHERE leaf_num = 175;
-- Returns: 145

-- Find roman numeral pages
SELECT leaf_num, book_page_number
FROM page_numbers
WHERE book_page_number GLOB '*[IVXLCDM]*'
ORDER BY leaf_num;

-- Find unnumbered pages (plates, blanks)
SELECT leaf_num FROM page_numbers
WHERE book_page_number IS NULL OR book_page_number = '';
```

## Finding Special Pages

### Table of Contents
Usually in the first 20 leafs:
```bash
# Search method
ia-utils search-catalog -c catalog.sqlite -q "contents"

# Direct text retrieval
ia-utils get-text -c catalog.sqlite -l 2-20
```

### Index
Usually at the end of the book:
```bash
# Search method
ia-utils search-catalog -c catalog.sqlite -q "index"

# If you know the index starts at leaf 937
ia-utils get-text -c catalog.sqlite -l 937-970
```

### Preface/Introduction
Usually in roman numeral pages:
```sql
SELECT leaf_num, book_page_number
FROM page_numbers
WHERE book_page_number GLOB '*[IVXLCDM]*'
ORDER BY leaf_num;
```

### Plates/Figures
Often have NULL page numbers or are between numbered pages:
```sql
-- Find potential plate pages (unnumbered)
SELECT leaf_num FROM page_numbers
WHERE book_page_number IS NULL
AND leaf_num > 10;  -- Skip front matter
```

## Working with Figure References

### Finding Figure References in Text
```bash
# Search for figure mentions
ia-utils search-catalog -c catalog.sqlite -q "Fig"
ia-utils search-catalog -c catalog.sqlite -q '"Fig. 210"'
ia-utils search-catalog -c catalog.sqlite -q "Plate"
```

### Locating Figures
Figures are typically on the same page or nearby. The search results give you the leaf number:

```bash
# Found reference to Fig. 210 on leaf 175
# View the page
ia-utils get-url -c catalog.sqlite -l 175 --viewer

# Download to examine
ia-utils get-page -c catalog.sqlite -l 175 -o fig210.jpg
```

### Index Lookup for Figures
If the book has a figure index:
```bash
# Get index text
ia-utils get-text -c catalog.sqlite -l 937-970 > index.txt
# Search the index for specific figures
grep -i "fig" index.txt
```

## Finding Plates and Color Images

Plates (especially color plates) require special discovery techniques because they often differ from regular text pages.

### Characteristics of Plate Pages
- **May lack page numbers**: Plates are often unnumbered (NULL in `page_numbers`)
- **May have tissue guards**: Thin protective pages adjacent to plates (usually blank or nearly blank)
- **Grouped together**: Color plates often appear in sections, not distributed through text
- **Referenced elsewhere**: Text mentions "see Plate XII" but plate may be many pages away

### Discovery Strategy

**1. Search for plate references in text:**
```bash
ia-utils search-catalog -c catalog.sqlite -q "Plate"
ia-utils search-catalog -c catalog.sqlite -q "plate"
ia-utils search-catalog -c catalog.sqlite -q "facing page"
```

**2. Find unnumbered pages (potential plates):**
```sql
-- Pages without printed page numbers
SELECT leaf_num FROM page_numbers
WHERE book_page_number IS NULL OR book_page_number = ''
ORDER BY leaf_num;
```

**3. Search for the subject near expected location:**
```bash
# If text says "liver" is on page 547, check nearby leaves
ia-utils search-catalog -c catalog.sqlite -q "liver"
# Then examine leaves around the matches
```

**4. Visual inspection (for LLMs with vision):**
```bash
# Download the page and adjacent pages
ia-utils get-page -c catalog.sqlite -l 600 -o check600.jpg
ia-utils get-page -c catalog.sqlite -l 601 -o check601.jpg
ia-utils get-page -c catalog.sqlite -l 602 -o check602.jpg
```

Look for:
- Full-page illustrations (no text or minimal captions)
- Color content (if the book has color plates)
- Tissue guards (blank or semi-transparent pages before/after)
- Figure captions at bottom of page

**5. Check adjacent leaves:**
When you find a reference to a figure, the actual image may be:
- On the same leaf
- On the facing page (leaf ± 1)
- On a nearby unnumbered leaf
- In a plate section at the front or back of the book

### Example: Finding a Plate
```bash
# 1. Search for subject
ia-utils search-catalog -c catalog.sqlite -q "liver" -l 10

# 2. Note the leaf numbers from results (e.g., leaf 612)

# 3. Get viewer URL for context
ia-utils get-url -c catalog.sqlite -l 612 --viewer

# 4. Download surrounding pages to find the actual plate
ia-utils get-page -c catalog.sqlite -l 611 -o before.jpg
ia-utils get-page -c catalog.sqlite -l 612 -o target.jpg
ia-utils get-page -c catalog.sqlite -l 613 -o after.jpg

# 5. Visually inspect to find the best illustration
```

## Navigating by Page Range

### Specifying Ranges
```bash
# Single page
-l 175          # Leaf 175
-b 145          # Book page 145

# Range
-l 100-120      # Leafs 100 through 120
-b 50-75        # Book pages 50 through 75

# List
-l 1,5,10,15    # Specific leafs

# Mixed
-l 1-5,10,20-25 # Ranges and individual
```

### Downloading Page Ranges
```bash
# As individual files
ia-utils get-pages -c catalog.sqlite -l 100-120 -p output/chapter5

# As ZIP
ia-utils get-pages -c catalog.sqlite -l 100-120 --zip -o chapter5.zip

# By book page
ia-utils get-pages -c catalog.sqlite -b 50-75 -p output/
```

### Getting Text for Range
```bash
ia-utils get-text -c catalog.sqlite -l 100-120
ia-utils get-text -c catalog.sqlite -l 100-120 -o chapter.txt
ia-utils get-text -c catalog.sqlite -l 100-120 --output-format json
```

## URL Formats

### Viewer URL (Recommended for Users)
```bash
ia-utils get-url -c catalog.sqlite -l 175 --viewer
# https://archive.org/details/b31362138/page/leaf175
```
Uses `leaf{n}` format (0-indexed). Best for giving users a link to explore interactively.

The BookReader also accepts book page numbers directly:
- `https://archive.org/details/b31362138/page/145` (book page 145)

**IMPORTANT**: Never output URLs with `n{n}` format (e.g., `/page/n175`). This internal BookReader format is unreliable outside the reader interface.

### Image URL
```bash
# Different sizes - all use leaf{n} format
ia-utils get-url -c catalog.sqlite -l 175 --size small
# https://archive.org/download/b31362138/page/leaf175_small.jpg

ia-utils get-url -c catalog.sqlite -l 175 --size medium
ia-utils get-url -c catalog.sqlite -l 175 --size large

ia-utils get-url -c catalog.sqlite -l 175 --size original
# https://archive.org/download/b31362138/b31362138_jp2.zip/b31362138_jp2/b31362138_0175.jp2
```

### PDF URL
```bash
# Full PDF
ia-utils get-url -c catalog.sqlite --pdf
# https://archive.org/download/b31362138/b31362138.pdf

# PDF with page anchor (leaf + 1 = PDF page)
ia-utils get-url -c catalog.sqlite -l 175 --pdf
# https://archive.org/download/b31362138/b31362138.pdf#page=176
```
Note: PDF pages are 1-indexed, so leaf N → PDF page N+1.

## Reading Images Directly (for LLMs)

When OCR quality is poor or you need to see a figure:

```bash
# Download medium quality (default, fast)
ia-utils get-page -c catalog.sqlite -l 175 -o page175.jpg

# Large for detailed examination
ia-utils get-page -c catalog.sqlite -l 175 --size large -o page175_large.jpg

# Apply enhancement for faded scans
ia-utils get-page -c catalog.sqlite -l 175 --autocontrast -o enhanced.jpg
```

Then use your image viewing capability to read the content directly.

## Common Navigation Patterns

### "Find page 145"
```bash
# Assumes book page number
ia-utils get-url -c catalog.sqlite -b 145 --viewer
```

### "Show me the femur diagram"
```bash
# Search for mentions
ia-utils search-catalog -c catalog.sqlite -q "femur" -l 10
# Take the most relevant leaf number, then
ia-utils get-page -c catalog.sqlite -l <number> -o femur.jpg
```

### "What's on pages 100-110?"
```bash
ia-utils get-text -c catalog.sqlite -l 100-110
# Or if they mean book pages:
# First find the leaf numbers
sqlite3 catalog.sqlite "SELECT leaf_num FROM page_numbers WHERE CAST(book_page_number AS INTEGER) BETWEEN 100 AND 110"
```

### "Go to the chapter on Nerves"
```bash
# Check TOC
ia-utils get-text -c catalog.sqlite -l 2-5
# Find page number in TOC output
# Convert to leaf and navigate
```

## Handling Edge Cases

### Missing Page Numbers
Some pages lack printed numbers:
```sql
SELECT leaf_num FROM page_numbers WHERE book_page_number IS NULL;
```

### Duplicate Page Numbers
Rare, but some books restart numbering:
```sql
SELECT leaf_num, book_page_number, COUNT(*) as count
FROM page_numbers
WHERE book_page_number IS NOT NULL
GROUP BY book_page_number
HAVING count > 1;
```

### Non-numeric Page Numbers
Roman numerals, letters, etc.:
```sql
SELECT leaf_num, book_page_number
FROM page_numbers
WHERE book_page_number IS NOT NULL
AND book_page_number NOT GLOB '[0-9]*'
ORDER BY leaf_num;
```
