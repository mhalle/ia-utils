# Collection Guide

Internet Archive organizes items into collections. Knowing which collections to search can dramatically improve results for specialized topics.

## Using Collections

```bash
# Search within a specific collection
ia-utils search-ia --collection wellcomelibrary -m texts --has-ocr -q "anatomy"

# Search multiple collections (use multiple --collection flags or search broadly)
ia-utils search-ia --collection medicalheritagelibrary -m texts -q "surgery"

# Find collections themselves
ia-utils search-ia -m collection -q "medical library"
```

**Important**: Always use `-m texts` when searching for books. This is the media type for books and documents.

## Medical & Health Collections

### Medical Heritage Library
**Collection ID**: `medicalheritagelibrary`

A consortium of major medical libraries providing historical medical texts.

```bash
ia-utils search-ia --collection medicalheritagelibrary -m texts --has-ocr -q "anatomy" -s downloads:desc
```

- **Strengths**: Large collection of historical medical texts, good OCR quality
- **Content**: Medical textbooks, journals, pharmacopoeias, surgical manuals
- **Time period**: Primarily 19th and early 20th century
- **Rights**: Generally clear rights status for historical materials

### Wellcome Library
**Collection ID**: `wellcomelibrary`

The Wellcome Library's digitized collection of medical history materials.

```bash
ia-utils search-ia --collection wellcomelibrary -m texts --has-ocr -q "surgery" -s downloads:desc
```

- **Strengths**: High-quality scans, excellent metadata, strong in medical history
- **Content**: Medical texts, anatomical atlases, history of medicine
- **Time period**: 16th-20th century
- **Rights**: Usually clear rights statements
- **Note**: Often uses ABBYY FineReader for OCR (good quality)

### US National Library of Medicine
**Collection ID**: `usnationallibraryofmedicine`

Historical materials from the NLM.

```bash
ia-utils search-ia --collection usnationallibraryofmedicine -m texts --has-ocr -q "pathology"
```

- **Strengths**: Authoritative medical content
- **Content**: Medical texts, public health documents, historical reports

## Scientific Collections

### Biodiversity Heritage Library
**Collection ID**: `biodiversity`

Natural history and biodiversity literature.

```bash
ia-utils search-ia --collection biodiversity -m texts --has-ocr -q "botanical" -s downloads:desc
```

- **Strengths**: Comprehensive natural history literature, taxonomic works
- **Content**: Flora, fauna, taxonomy, natural history journals
- **Time period**: 18th-20th century
- **Note**: Excellent for botanical and zoological illustrations

### Smithsonian Libraries
**Collection ID**: `smithsonian`

Materials from the Smithsonian Institution libraries.

```bash
ia-utils search-ia --collection smithsonian -m texts --has-ocr -q "natural history"
```

- **Strengths**: Broad scientific coverage, museum-quality materials
- **Content**: Natural history, art, science, technology

## General Book Collections

### American Libraries
**Collection ID**: `americana`

One of the largest collections of American books and documents.

```bash
ia-utils search-ia --collection americana -m texts --has-ocr -q "topic" -s downloads:desc
```

- **Strengths**: Massive collection, diverse content
- **Content**: Everything American - books, pamphlets, government docs
- **Note**: Quality varies widely; check downloads and OCR before investing time

### Google Books
**Collection ID**: `google-books`

Books digitized by Google and contributed to IA.

```bash
ia-utils search-ia --collection google-books -m texts --has-ocr -q "topic"
```

- **Strengths**: Large scale, many rare books
- **Weaknesses**:
  - Older scans (typically from early-mid 2000s digitization efforts)
  - Generally lower resolution than more recent scans
  - Sometimes cropped images, variable OCR quality
  - Image quality can be noticeably worse than Wellcome Library or recent IA scans
- **Note**: Some items may have access restrictions
- **Tip**: When the same work is available from multiple sources, prefer Wellcome Library or recent IA scans over Google Books for better image quality

### University Collections

Many universities have contributed collections:

| Collection ID | Institution |
|---------------|-------------|
| `universityofcalifornia` | University of California |
| `cornell` | Cornell University |
| `princeton` | Princeton University |
| `harvardpublicdomain` | Harvard (public domain) |
| `bostonpubliclibrary` | Boston Public Library |

## European Collections

### European Libraries
**Collection ID**: `europeanlibraries`

Aggregated European library content.

```bash
ia-utils search-ia --collection europeanlibraries -m texts --has-ocr -q "topic" --lang ger
```

- **Strengths**: European language materials, historical texts
- **Content**: Multi-language, strong in German, French, Italian
- **Note**: Good for finding non-English editions of scientific works

## Searching Strategy by Subject

### Medical/Anatomical Texts
```bash
# Best collections for medical content
ia-utils search-ia --collection wellcomelibrary -m texts --has-ocr -q "anatomy atlas" -s downloads:desc
ia-utils search-ia --collection medicalheritagelibrary -m texts --has-ocr -q "surgery" -s downloads:desc
```

### Natural History/Biology
```bash
# Best collections for natural history
ia-utils search-ia --collection biodiversity -m texts --has-ocr -q "ornithology" -s downloads:desc
ia-utils search-ia --collection smithsonian -m texts --has-ocr -q "entomology"
```

### Historical Science
```bash
# Broad search across scientific collections
ia-utils search-ia -q "chemistry" --year 1800-1900 -m texts --has-ocr -s downloads:desc
```

### Non-English Scientific Texts
```bash
# German medical texts
ia-utils search-ia --collection europeanlibraries -m texts --has-ocr --lang ger -q "anatomie"

# French scientific texts
ia-utils search-ia -m texts --has-ocr --lang fre -q "physiologie" -s downloads:desc
```

## Collection Quality Indicators

When choosing between collections, consider:

| Factor | How to Check |
|--------|--------------|
| OCR quality | `ia-utils info <id>` - check `ocr` field for engine |
| Scan quality | Download a sample page, check visually |
| Metadata quality | Check if title, creator, date are accurate |
| Rights clarity | Check `rights` field for clear status |
| Popularity | Sort by `downloads:desc` - popular items often better quality |

**OCR Engine Quality (general ranking):**
1. ABBYY FineReader 11+ (best)
2. ABBYY FineReader 8-10 (good)
3. Tesseract (variable)
4. Unknown/unspecified (check manually)

## Tips for LLMs

1. **Start with specialized collections** when the subject is clear (medical → wellcomelibrary, natural history → biodiversity)

2. **Fall back to broad search** if specialized collections don't have what you need:
   ```bash
   ia-utils search-ia -q "topic" -m texts --has-ocr -s downloads:desc
   ```

3. **Check multiple collections** - the same work may be in several with different scan quality

4. **Note the collection in results** - helps explain provenance to users

5. **Use `--collection` with other filters** for precise results:
   ```bash
   ia-utils search-ia --collection wellcomelibrary -m texts --has-ocr \
     -q "anatomy" --year 1900-1940 --lang eng -s downloads:desc
   ```
