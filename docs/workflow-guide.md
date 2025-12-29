# Workflow Guide

This guide covers common workflows for discovering and extracting content from Internet Archive books.

## Workflow 1: Finding the Best Edition of a Book

When a user wants a specific text (e.g., "Gray's Anatomy"), there are often multiple editions and scans. Here's how to help them choose:

### Step 1: Search by Title/Author
```bash
ia-utils search-ia -q "anatomy" --creator "Gray" -m texts --has-ocr -s downloads:desc -l 20
```

### Step 2: Compare Editions
Key factors to evaluate:
- **rights**: Check copyright status - prefer clear public domain or open licenses
- **downloads**: Higher = more popular, often better quality
- **date**: Different editions have different content
- **ocr**: Check OCR engine (ABBYY FineReader 11 > 8 > tesseract for older texts)
- **collection**: wellcomelibrary, medicalheritagelibrary often have good scans
- **format**: Look for "hOCR" in format list for best searchability

Common rights values:
- "Public Domain" / "Public Domain Mark" - freely usable
- "No Known Copyright" - likely safe to use
- "Copyright Not Cleared" - may have restrictions
- Rights statement URLs (e.g., rightsstatements.org) - check the linked page

### Step 3: Inspect Candidates
```bash
ia-utils info anatomyofhumanbo1918gray
ia-utils info anatomydescript00gray
```

Compare:
- `imagecount`: More pages might mean more complete
- `description`: Check for "illustrated", edition number
- `rights`: Some items may have access restrictions

### Step 4: Sample the Content
Create a quick catalog and check OCR quality:
```bash
ia-utils create-catalog <best_candidate> -d ./test/
ia-utils search-catalog -c ./test/*.sqlite -q "common term"
ia-utils get-text -c ./test/*.sqlite -l 50
```

## Workflow 2: Finding Content Within a Book

### Finding the Table of Contents
```bash
# TOC is usually in the first 20 pages
ia-utils search-catalog -c catalog.sqlite -q "contents" -l 10
ia-utils get-text -c catalog.sqlite -l 2-10
```

### Finding the Index
```bash
# Index is usually at the end
ia-utils search-catalog -c catalog.sqlite -q "index" -l 10
# Look for high leaf numbers in results
ia-utils get-text -c catalog.sqlite -l 937  # Example index page
```

### Finding Figures and Plates
```bash
# Search for figure references
ia-utils search-catalog -c catalog.sqlite -q "Fig"
ia-utils search-catalog -c catalog.sqlite -q "Plate"

# Or search for specific figure numbers
ia-utils search-catalog -c catalog.sqlite -q '"Fig. 210"'
```

### Looking Up a Term in the Index
```bash
# Get index pages
ia-utils search-catalog -c catalog.sqlite -q "index"
# Note the leaf numbers, then get the text
ia-utils get-text -c catalog.sqlite -l 937-970
# Search within the output for your term
```

## Workflow 3: Navigating Between Page Numbers

### Book Page to Leaf Number
```bash
# Using the command
ia-utils get-url -c catalog.sqlite -b 145
# Returns the image URL for book page 145

# Or query directly
sqlite3 catalog.sqlite "SELECT leaf_num FROM page_numbers WHERE book_page_number = '145'"
```

### Leaf Number to Book Page
```bash
sqlite3 catalog.sqlite "SELECT book_page_number FROM page_numbers WHERE leaf_num = 175"
```

### Finding Roman Numeral Pages (Front Matter)
```bash
sqlite3 catalog.sqlite "SELECT leaf_num, book_page_number FROM page_numbers WHERE book_page_number LIKE '%I%' ORDER BY leaf_num LIMIT 30"
```

## Workflow 4: Examining Poor OCR or Figures

When OCR quality is insufficient or you need to see a figure:

### Download and View Page
```bash
# Download medium quality (good for viewing)
ia-utils get-page -c catalog.sqlite -l 175 -o page175.jpg

# For detailed figures, use large or original
ia-utils get-page -c catalog.sqlite -l 175 --size large -o page175_large.jpg
ia-utils get-page -c catalog.sqlite -l 175 --size original -o page175.jp2
```

### Apply Image Enhancement
```bash
# Autocontrast for faded scans
ia-utils get-page -c catalog.sqlite -l 175 --autocontrast -o enhanced.jpg

# Cutoff for very faded text
ia-utils get-page -c catalog.sqlite -l 175 --cutoff 5 -o enhanced.jpg
```

### Provide User with Viewer Link
```bash
# Interactive viewer (best for exploration)
ia-utils get-url -c catalog.sqlite -l 175 --viewer
# Output: https://archive.org/details/b31362138/page/leaf175

# Direct image URL
ia-utils get-url -c catalog.sqlite -l 175 --size large
```

## Workflow 5: Bulk Export

### Export Multiple Pages as Images
```bash
# Individual files
ia-utils get-pages -c catalog.sqlite -l 100-120 -p output/chapter5

# As ZIP archive
ia-utils get-pages -c catalog.sqlite -l 100-120 --zip -o chapter5.zip

# All pages as ZIP
ia-utils get-pages -c catalog.sqlite --all --zip
```

### Export Text
```bash
# Single page
ia-utils get-text -c catalog.sqlite -l 175

# Range of pages
ia-utils get-text -c catalog.sqlite -l 100-120 -o chapter5.txt

# As JSON for processing
ia-utils get-text -c catalog.sqlite -l 100-120 --output-format json -o chapter5.json
```

### Download Full PDF
```bash
ia-utils get-pdf -c catalog.sqlite -o book.pdf
# Or directly by ID
ia-utils get-pdf b31362138
```

## Workflow 6: Comparing Scans of the Same Work

When multiple institutions have scanned the same book:

```bash
# Find all versions
ia-utils search-ia -q "Hand atlas human anatomy Spalteholz" -m texts --has-ocr -l 20

# Create catalogs for comparison
ia-utils create-catalog b31362138 -d ./compare/
ia-utils create-catalog b29336211 -d ./compare/

# Compare OCR quality
ia-utils info ./compare/*.sqlite

# Sample the same page from each
ia-utils search-catalog -c ./compare/scan1.sqlite -q "femur" -l 3
ia-utils search-catalog -c ./compare/scan2.sqlite -q "femur" -l 3
```

Factors to compare:
- `block_count`: More blocks usually means better OCR segmentation
- OCR confidence (if using --full hOCR catalogs)
- Visual quality of pages

## Workflow 7: Building a Research Corpus

For systematic research across multiple books:

```bash
# Search across IA
ia-utils search-ia -q "anatomy" --year 1850-1920 -m texts --has-ocr -s downloads:desc -l 50 -o corpus_candidates.csv

# Build catalogs for selected items
for id in item1 item2 item3; do
  ia-utils create-catalog $id -d ./corpus/
done

# Search across all catalogs
for catalog in ./corpus/*.sqlite; do
  echo "=== $catalog ==="
  ia-utils search-catalog -c "$catalog" -q "your search term" -l 5
done
```

## Tips for LLMs

1. **Start broad, narrow down**: Begin with relaxed searches, then add filters
2. **Check downloads first**: Popular items are usually better quality
3. **Verify OCR quality early**: Create catalog and test search before deep dive
4. **Use viewer links**: Give users `--viewer` URLs so they can explore themselves
5. **Fall back to images**: When OCR fails, download and view the page directly
6. **Map pages carefully**: Always clarify if user means leaf or book page number
