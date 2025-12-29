# Catalog Reference

Complete reference for building and using ia-utils catalogs.

## Creating Catalogs

### Basic Usage
```bash
ia-utils create-catalog <identifier> -d ./catalogs/
ia-utils create-catalog b31362138 -d ./catalogs/
ia-utils create-catalog https://archive.org/details/b31362138 -d ./catalogs/
```

### Output Options
```bash
-d ./catalogs/                    # Output directory
-o custom_name.sqlite             # Custom filename
# Default: {author}-{title}-{year}_{ia_id}.sqlite
```

### Catalog Modes

#### Default Mode (searchtext)
```bash
ia-utils create-catalog b31362138 -d ./catalogs/
```
- **Speed**: Fast (downloads pre-indexed search text)
- **Features**: Basic text blocks, page-level FTS
- **Size**: Smaller (~9MB for 976 pages)
- **Best for**: Quick searches, most use cases

#### Full Mode (hOCR)
```bash
ia-utils create-catalog b31362138 -d ./catalogs/ --full
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
ia-utils -v create-catalog b31362138 -d ./catalogs/
```
Shows detailed progress: download status, parsing progress, block counts.

## Catalog Information

### Basic Info
```bash
ia-utils info catalog.sqlite
ia-utils info -c catalog.sqlite
```

Output includes:
- `filename`: Catalog filename
- `identifier`: IA identifier
- `title`, `creator`, `date`: Book metadata
- `description`: Full description
- `collection`: IA collections
- `imagecount`: Total page scans
- `block_count`: OCR text blocks
- `ocr`: OCR engine used
- `size_mb`: Catalog file size

### All Fields
```bash
ia-utils info catalog.sqlite -f '*' --output-format json
```

## Using Catalogs

### Search
```bash
ia-utils search-catalog -c catalog.sqlite -q "term"
ia-utils search-catalog -c catalog.sqlite -q "term" --blocks
```

### Get Text
```bash
ia-utils get-text -c catalog.sqlite -l 175
ia-utils get-text -c catalog.sqlite -l 100-110
ia-utils get-text -c catalog.sqlite -l 1,5,10
```

### Get Pages
```bash
ia-utils get-page -c catalog.sqlite -l 175
ia-utils get-page -c catalog.sqlite -b 145  # By book page
ia-utils get-pages -c catalog.sqlite -l 1-20 -p output/
```

### Get URLs
```bash
ia-utils get-url -c catalog.sqlite -l 175
ia-utils get-url -c catalog.sqlite -l 175 --viewer
ia-utils get-url -c catalog.sqlite --pdf
```

### Get PDF
```bash
ia-utils get-pdf -c catalog.sqlite
ia-utils get-pdf -c catalog.sqlite -o custom.pdf
```

## Rebuilding Catalogs

If you need to regenerate indexes:
```bash
ia-utils rebuild-catalog catalog.sqlite
ia-utils rebuild-catalog catalog.sqlite --full  # Full regeneration
```

## Direct Database Access

Catalogs are SQLite databases that can be queried directly:

```bash
sqlite3 catalog.sqlite ".tables"
sqlite3 catalog.sqlite ".schema text_blocks"
sqlite3 catalog.sqlite "SELECT COUNT(*) FROM text_blocks"
```

See [Database Schema](database-schema.md) for complete table documentation.

## Catalog Comparison

When you have multiple catalogs (e.g., different editions):

```bash
# Compare basic stats
for f in ./catalogs/*.sqlite; do
  echo "=== $f ==="
  ia-utils info "$f"
  echo ""
done

# Compare search results
for f in ./catalogs/*.sqlite; do
  echo "=== $f ==="
  ia-utils search-catalog -c "$f" -q "femur" -l 3
  echo ""
done
```

## Best Practices

1. **Choose mode wisely**:
   - Use default for most searches
   - Use `--full` only when you need confidence scores or layout info

2. **Organize catalogs**:
   - Keep catalogs in a dedicated directory
   - Default naming is informative: `author-title-year_id.sqlite`

3. **Check quality early**:
   - After creating catalog, run a test search
   - Check `block_count` - more blocks usually means better OCR

4. **Use catalogs for repeated access**:
   - Creating a catalog once is faster than repeated API calls
   - Catalogs work offline after creation

5. **Clean up test catalogs**:
   - Development catalogs can be large
   - Delete unused catalogs to save space
