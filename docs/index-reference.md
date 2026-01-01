# Index Reference

Complete reference for building and using ia-utils indexes.

## Creating Indexes

### Basic Usage
```bash
ia-utils create-index <identifier> -d ./indexes/
ia-utils create-index b31362138 -d ./indexes/
ia-utils create-index https://archive.org/details/b31362138 -d ./indexes/
```

### Output Options
```bash
-d ./indexes/                     # Output directory
-o custom_name.sqlite             # Custom filename
# Default: {author}-{title}-{year}_{ia_id}.sqlite
```

### Index Modes

#### Default Mode (searchtext)
```bash
ia-utils create-index b31362138 -d ./indexes/
```
- **Speed**: Fast (downloads pre-indexed search text)
- **Features**: Basic text blocks, page-level FTS
- **Size**: Smaller (~9MB for 976 pages)
- **Best for**: Quick searches, most use cases

#### Full Mode (hOCR)
```bash
ia-utils create-index b31362138 -d ./indexes/ --full
```
- **Speed**: Slow (downloads and parses full hOCR HTML)
- **Features**: Bounding boxes, font sizes, confidence scores
- **Size**: Larger (~12MB for 976 pages)
- **Best for**: Layout analysis, finding typography differences, quality assessment

#### DjVu Mode (fallback)
Used automatically when searchtext is unavailable:
- **Features**: Confidence scores, word-level data
- **Best for**: Items without searchtext index

### Verbose Output
```bash
ia-utils -v create-index b31362138 -d ./indexes/
```
Shows detailed progress: download status, parsing progress, block counts.

## Index Information

### Basic Info
```bash
ia-utils info index.sqlite
ia-utils info -i index.sqlite
```

Output includes:
- `filename`: Index filename
- `identifier`: IA identifier
- `title`, `creator`, `date`: Book metadata
- `description`: Full description
- `collection`: IA collections
- `imagecount`: Total page scans
- `block_count`: OCR text blocks
- `ocr`: OCR engine used
- `size_mb`: Index file size

### All Fields
```bash
ia-utils info index.sqlite -f '*' --output-format json
```

## Using Indexes

### Search
```bash
ia-utils search-index -i index.sqlite -q "term"
ia-utils search-index -i index.sqlite -q "term" --blocks
```

### Get Text
```bash
ia-utils get-text -i index.sqlite -l 175
ia-utils get-text -i index.sqlite -l 100-110
ia-utils get-text -i index.sqlite -l 1,5,10
```

### Get Pages
```bash
ia-utils get-page -i index.sqlite -l 175
ia-utils get-page -i index.sqlite -b 145  # By book page
ia-utils get-pages -i index.sqlite -l 1-20 -p output/
```

### Get URLs
```bash
ia-utils get-url -i index.sqlite -l 175
ia-utils get-url -i index.sqlite -l 175 --viewer
ia-utils get-url -i index.sqlite --pdf
```

### Get PDF
```bash
ia-utils get-pdf -i index.sqlite
ia-utils get-pdf -i index.sqlite -o custom.pdf
```

## Rebuilding Indexes

If you need to regenerate indexes:
```bash
ia-utils rebuild-index index.sqlite
ia-utils rebuild-index index.sqlite --full  # Full regeneration
```

## Direct Database Access

Indexes are SQLite databases that can be queried directly:

```bash
sqlite3 index.sqlite ".tables"
sqlite3 index.sqlite ".schema text_blocks"
sqlite3 index.sqlite "SELECT COUNT(*) FROM text_blocks"
```

See [Database Schema](database-schema.md) for complete table documentation.

## Index Comparison

When you have multiple indexes (e.g., different editions):

```bash
# Compare basic stats
for f in ./indexes/*.sqlite; do
  echo "=== $f ==="
  ia-utils info "$f"
  echo ""
done

# Compare search results
for f in ./indexes/*.sqlite; do
  echo "=== $f ==="
  ia-utils search-index -i "$f" -q "femur" -l 3
  echo ""
done
```

## Best Practices

1. **Choose mode wisely**:
   - Use default for most searches
   - Use `--full` only when you need confidence scores or layout info

2. **Organize indexes**:
   - Keep indexes in a dedicated directory
   - Default naming is informative: `author-title-year_id.sqlite`

3. **Check quality early**:
   - After creating index, run a test search
   - Check `block_count` - more blocks usually means better OCR

4. **Use indexes for repeated access**:
   - Creating an index once is faster than repeated API calls
   - Indexes work offline after creation

5. **Clean up test indexes**:
   - Development indexes can be large
   - Delete unused indexes to save space
