# Troubleshooting Guide

Common problems and solutions when using ia-utils.

## Index Creation Issues

### "No OCR text available"
**Symptom**: `create-index` fails saying no searchable text found.

**Causes & Solutions**:
1. **Item has no OCR**: Check `ia-utils info <id>` - look for `ocr` field
   - If empty, the item wasn't OCR'd - no text search possible
   - You can still download pages/PDF, but no text search

2. **Item is print-disabled**: Some items have access restrictions
   - Check the `rights` field
   - Try a different edition of the same work

3. **Wrong media type**: Ensure item is `texts` not `audio` or `image`

### Index creation hangs or times out
**Symptom**: `create-index` runs for a very long time.

**Solutions**:
1. **Large book**: Books with 1000+ pages take longer. Use `-v` to see progress:
   ```bash
   ia-utils -v create-index <id> -d ./indexes/
   ```

2. **Network issues**: IA servers may be slow. Try again later.

3. **Use default mode**: Don't use `--full` unless you need hOCR features:
   ```bash
   # Fast (default)
   ia-utils create-index <id> -d ./indexes/

   # Slow (only if needed)
   ia-utils create-index <id> -d ./indexes/ --full
   ```

### "File not found" or download errors
**Symptom**: Error downloading files from IA.

**Solutions**:
1. **Check identifier**: Verify the ID exists:
   ```bash
   ia-utils info <id>
   ```

2. **Item may be temporarily unavailable**: IA sometimes has outages. Try later.

3. **Item may have been removed**: Search for alternative editions.

## Search Issues

### Search returns no results
**Symptom**: `search-index` returns nothing for terms you know exist.

**Solutions**:
1. **Check spelling**: OCR may have errors. Try variations:
   ```bash
   ia-utils search-index -i index.sqlite -q "femur"
   ia-utils search-index -i index.sqlite -q "femnr"  # OCR error
   ia-utils search-index -i index.sqlite -q "fem*"   # Prefix search
   ```

2. **Try simpler terms**: Break up complex queries:
   ```bash
   # Instead of
   ia-utils search-index -i index.sqlite -q "anterior cruciate ligament"
   # Try
   ia-utils search-index -i index.sqlite -q "cruciate"
   ```

3. **Check the index has content**:
   ```bash
   sqlite3 index.sqlite "SELECT COUNT(*) FROM text_blocks"
   ```

4. **Hyphenated terms**: By default these are auto-quoted. Use `--raw` if needed:
   ```bash
   ia-utils search-index -i index.sqlite -q "self-adjusting" --raw
   ```

### Search returns garbled text
**Symptom**: Snippets are unreadable or nonsensical.

**Cause**: Poor OCR quality.

**Solutions**:
1. **Check OCR confidence** (hOCR indexes only):
   ```sql
   sqlite3 index.sqlite "SELECT AVG(avg_confidence) FROM text_blocks"
   ```
   - Below 50%: Poor quality, expect many errors
   - 50-70%: Moderate, some errors
   - Above 70%: Good quality

2. **View the page directly**:
   ```bash
   ia-utils get-page -i index.sqlite -l <leaf> -o check.jpg
   ```

3. **Try a different edition**: Search for alternatives with better scans.

### FTS5 syntax errors
**Symptom**: Error about query syntax.

**Cause**: Special characters interpreted as FTS operators.

**Solutions**:
1. **Quote phrases**:
   ```bash
   ia-utils search-index -i index.sqlite -q '"exact phrase"'
   ```

2. **Use `--raw` carefully**: Only when you need FTS operators:
   ```bash
   ia-utils search-index -i index.sqlite -q "term1 AND term2" --raw
   ```

## Page/URL Issues

### Wrong page displayed
**Symptom**: URL shows different content than expected.

**Causes & Solutions**:
1. **Leaf vs book page confusion**:
   - `-l 175` = leaf 175 (physical scan)
   - `-b 145` = book page 145 (printed number)
   ```bash
   # Check the mapping
   sqlite3 index.sqlite "SELECT leaf_num, book_page_number FROM page_numbers WHERE leaf_num = 175"
   ```

2. **Book page number is wrong in source**: OCR may have misread the page number
   - Use leaf numbers for reliability
   - Verify visually if critical

### PDF page doesn't match
**Symptom**: PDF#page=N shows wrong page.

**Cause**: PDF pages are 1-indexed, leaves are 0-indexed.

**Solution**: PDF page = leaf + 1
```bash
# Leaf 175 → PDF page 176
ia-utils get-url -i index.sqlite -l 175 --pdf
# Returns: ...pdf#page=176
```

### Image won't download
**Symptom**: `get-page` fails or returns error.

**Solutions**:
1. **Check leaf number is valid**:
   ```bash
   ia-utils info -i index.sqlite
   # Check imagecount
   ```

2. **Try different size**:
   ```bash
   ia-utils get-page -i index.sqlite -l 175 --size medium
   ia-utils get-page -i index.sqlite -l 175 --size small
   ```

3. **Network issue**: Try again or check IA status.

## Database Issues

### "Database is locked"
**Symptom**: SQLite error about locked database.

**Cause**: Another process is using the index.

**Solution**: Close other applications using the file, or wait.

### "No such table"
**Symptom**: SQL query fails with missing table error.

**Cause**: Querying wrong index type or corrupted index.

**Solutions**:
1. **Check index mode**:
   ```bash
   sqlite3 index.sqlite "SELECT * FROM index_metadata"
   ```

2. **Rebuild if corrupted**:
   ```bash
   ia-utils rebuild-index index.sqlite
   ```

### Index file is very large
**Symptom**: Index is unexpectedly large (100MB+).

**Cause**: Using `--full` mode on large book.

**Solutions**:
1. **Use default mode** unless you need hOCR features
2. **Delete and recreate** without `--full`:
   ```bash
   rm index.sqlite
   ia-utils create-index <id> -d ./indexes/
   ```

## Access and Rights Issues

### "Item not available"
**Symptom**: Can't access item, error about availability.

**Causes**:
1. **Print-disabled**: Item is borrowable only, not freely downloadable
2. **Geographic restriction**: Some items restricted by region
3. **Removed**: Item was taken down

**Solutions**:
1. **Search for alternative editions**:
   ```bash
   ia-utils search-ia -q "title words" -m texts --has-ocr -s downloads:desc
   ```

2. **Check different collections**: Same work may be in multiple collections with different access

3. **Use `--include-unavailable`** to see what exists:
   ```bash
   ia-utils search-ia -q "title" --include-unavailable
   ```

### Rights unclear
**Symptom**: Not sure if item can be used.

**Solution**: Check multiple fields:
```bash
ia-utils info <id> -f rights -f possible-copyright-status -f licenseurl
```

Common safe values:
- "Public Domain Mark"
- "No Known Copyright"
- "CC0" or Creative Commons licenses
- Empty rights with pre-1928 date (likely public domain in US)

## Performance Tips

### Slow searches
1. **Use page-level search** (default) instead of `--blocks`
2. **Limit results**: `-l 20` instead of `-l 100`
3. **Use FTS, not LIKE**: FTS is optimized; avoid raw SQL with `LIKE '%term%'`

### Slow index creation
1. **Avoid `--full`** unless needed
2. **Check disk space**: Index creation needs temp space
3. **Use SSD** if possible for faster I/O

## Getting Help

If problems persist:
1. **Check ia-utils version**: `ia-utils --version`
2. **Use verbose mode**: `ia-utils -v <command>`
3. **Check IA status**: https://status.archive.org/
4. **Report issues**: https://github.com/mhalle/ia-utils/issues
