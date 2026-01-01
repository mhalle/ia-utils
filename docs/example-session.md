# Example Session: Exploring Spalteholz's Anatomy Atlas

This document shows a complete example session exploring a medical anatomy atlas.

## The Book

**Spalteholz's Hand Atlas of Human Anatomy** (1933)
- IA Identifier: `b31362138`
- A comprehensive anatomy atlas with detailed illustrations
- 976 page scans, 3 volumes bound together

## Setup

```bash
# Create working directory
mkdir -p indexes

# Create index (takes ~30 seconds)
uv run --with git+https://github.com/mhalle/ia-utils.git \
  ia-utils create-index b31362138 -d ./indexes/
```

Output:
```
Building index for: b31362138 [fast (searchtext)]
...
✓ Database created: indexes/spalteholz-hand-atlas-human-anatomy-1933_b31362138.sqlite
```

## Exploring the Book

### Check Book Info
```bash
ia-utils info indexes/spalteholz-hand-atlas-human-anatomy-1933_b31362138.sqlite
```

Output:
```
filename: spalteholz-hand-atlas-human-anatomy-1933_b31362138.sqlite
identifier: b31362138
title: Hand atlas of human anatomy
creator: Spalteholz, Werner, 1861-1940
date: 1933
imagecount: 976
block_count: 29575
ocr: ABBYY FineReader 11.0 (Extended OCR)
```

### Find the Table of Contents
```bash
ia-utils get-text -i indexes/spalteholz*.sqlite -l 2-3
```

Output shows the complete TOC with page references:
- BONES: pages vii-169
- JOINTS AND LIGAMENTS: pages 170-246
- MUSCLES AND FASCIAE: pages 255-382
- And more...

### Search for Femur Content
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q "femur" -l 5
```

Output:
```
leaf: 175
page: 145
snippet: ...Right thigh bone, →femur←, inferior extremity, from in front...
url: https://archive.org/details/b31362138/page/leaf175

leaf: 251
page: 221
snippet: ...The capsule is attached to the →femur← in front close above...
url: https://archive.org/details/b31362138/page/leaf251
```

### View a Page
```bash
# Get viewer URL for user
ia-utils get-url -i indexes/spalteholz*.sqlite -l 175 --viewer
# Output: https://archive.org/details/b31362138/page/leaf175

# Download to view directly
ia-utils get-page -i indexes/spalteholz*.sqlite -l 175 -o femur-page.jpg
```

### Find the Circle of Willis
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q '"circle of willis"'
```

Output:
```
leaf: 486
page: 422
snippet: ...arises the circulus arteriosus [Willisi] (O. T. →circle of Willis←)
         which lies over the sella turcica...
```

### Access the Index
```bash
# The index starts at leaf 937 (page 869)
ia-utils get-text -i indexes/spalteholz*.sqlite -l 937
```

Output shows alphabetized index entries with page references.

## Direct Database Queries

### Map Book Page to Leaf
```bash
sqlite3 indexes/spalteholz*.sqlite \
  "SELECT leaf_num FROM page_numbers WHERE book_page_number = '145'"
# Output: 175
```

### Find OCR Statistics
```bash
# For the hOCR index
sqlite3 indexes/spalteholz-hocr.sqlite \
  "SELECT AVG(avg_confidence), MIN(avg_confidence), MAX(avg_confidence) FROM text_blocks WHERE avg_confidence IS NOT NULL"
# Output: 54.44|0.0|100.0
```

### Get Page Text with FTS Highlighting
```bash
sqlite3 indexes/spalteholz*.sqlite \
  "SELECT page_id, snippet(pages_fts, 0, '→', '←', '...', 30) FROM pages_fts WHERE pages_fts MATCH 'nerve NEAR muscle' LIMIT 5"
```

## Downloading Content

### Get a Range of Pages
```bash
# As individual files
ia-utils get-pages -i indexes/spalteholz*.sqlite -l 100-110 -p output/anatomy

# As ZIP
ia-utils get-pages -i indexes/spalteholz*.sqlite -l 100-110 --zip -o chapter.zip
```

### Get the PDF
```bash
ia-utils get-pdf -i indexes/spalteholz*.sqlite
# Downloads: spalteholz-hand-atlas-human-anatomy-1933_b31362138.pdf
```

## Tips for This Specific Book

1. **Page numbers start at leaf 30** (page 1 of main content)
2. **Roman numerals for preface**: leaves 12-28
3. **Index is at leaves 937-970** (pages 869-902)
4. **Figures are numbered sequentially** throughout the book
5. **OCR quality is good** (ABBYY FineReader 11.0)

## Sample User Interactions

### "Where can I find information about the hip joint?"
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q "hip joint" -l 5
```
→ Found on pages 220-231 (hip joint articulatio coxae)

### "Show me figure 210"
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q "210"
# Find the reference, then download the page
ia-utils get-page -i indexes/spalteholz*.sqlite -l 175 -o fig210.jpg
```

### "What page is the Circle of Willis on?"
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q '"circle of willis"'
# Page 422 (leaf 486)
ia-utils get-url -i indexes/spalteholz*.sqlite -l 486 --viewer
```

---

## Worked Example: Finding Images of the Lobes of the Liver

This example demonstrates the plate-finding techniques: searching for references, examining adjacent pages, and visually inspecting to locate illustrations.

### Step 1: Search for the topic in both books

**Spalteholz:**
```bash
ia-utils search-index -i indexes/spalteholz*.sqlite -q "liver" -l 10
ia-utils search-index -i indexes/spalteholz*.sqlite -q "hepatis" -l 10
```

Results show liver content around leaves 615-630.

**Cunningham:**
```bash
ia-utils search-index -i indexes/cunningham*.sqlite -q "lobes liver" -l 10
```

Results mention "Fig. 938" on pages around leaf 1227-1229.

### Step 2: Download and visually inspect candidate pages

```bash
# Spalteholz - check the liver section
ia-utils get-page -i indexes/spalteholz*.sqlite -l 615 -o liver_615.jpg
ia-utils get-page -i indexes/spalteholz*.sqlite -l 616 -o liver_616.jpg

# Cunningham - search mentions Fig. 938, look for it
ia-utils get-page -i indexes/cunningham*.sqlite -l 1224 -o liver_1224.jpg
ia-utils get-page -i indexes/cunningham*.sqlite -l 1229 -o liver_1229.jpg
```

Visual inspection reveals:
- Spalteholz leaf 615: Fig. 630 - Liver from front
- Spalteholz leaf 616: Fig. 631 - Liver from above (shows lobes labeled)
- Cunningham leaf 1224: Fig. 936 - Liver from front
- Cunningham leaf 1229: Fig. 938 - Inferior surface (best lobe view)

### Step 3: Present results to user

**Spalteholz's Hand Atlas (1933)** - b31362138

| Figure | Description | Leaf | Page | Viewer URL |
|--------|-------------|------|------|------------|
| Fig. 630 | Liver with peritoneum, from front | 615 | 547 | https://archive.org/details/b31362138/page/leaf615 |
| Fig. 631 | Liver from above, lobes labeled | 616 | 548 | https://archive.org/details/b31362138/page/leaf616 |

Rights: "It is possible this Item is protected by copyright" (check rightsstatements.org)

**Cunningham's Text-book (1914)** - cunninghamstextb00cunn

| Figure | Description | Leaf | Page | Viewer URL |
|--------|-------------|------|------|------------|
| Fig. 936 | Liver from front | 1224 | 1188 | https://archive.org/details/cunninghamstextb00cunn/page/leaf1224 |
| Fig. 937 | Liver from behind | 1225 | 1189 | https://archive.org/details/cunninghamstextb00cunn/page/leaf1225 |
| Fig. 938 | Inferior surface with lobes | 1229 | 1193 | https://archive.org/details/cunninghamstextb00cunn/page/leaf1229 |

Rights: No restriction noted (1914 publication, likely public domain)

### Key Techniques Used

1. **Searched for subject terms** ("liver", "hepatis", "lobes liver")
2. **Noted figure references** in search results (text mentions "Fig. 938")
3. **Downloaded adjacent pages** to find the actual illustration
4. **Visually inspected** pages to confirm content and quality
5. **Provided both formats**: viewer URLs for exploration, leaf numbers for commands
6. **Included rights information** to help user choose appropriate source
