# Working with Multi-Volume Works

Many historical books, especially encyclopedias, atlases, and comprehensive treatises, were published in multiple volumes. On Internet Archive, these volumes are typically separate items that need to be identified and worked with individually.

## Identifying Multi-Volume Works

### Volume Field
Some items have a `volume` field in their metadata:

```bash
ia-utils search-ia -q "Spalteholz" -m texts --has-ocr -f identifier -f title -f date -f volume
```

Example output:
```
identifier: handatlashumananatomy1923v1
title: Hand-atlas of human anatomy
date: 1923
volume: 1

identifier: handatlashumananatomy1923v2
title: Hand-atlas of human anatomy
date: 1923
volume: 2

identifier: handatlashumananatomy1923v3
title: Hand-atlas of human anatomy
date: 1923
volume: 3
```

### Identifier Patterns
Volumes are often indicated in the identifier:

| Pattern | Example | Meaning |
|---------|---------|---------|
| `_v1`, `_v2` | `work_v1`, `work_v2` | Volume 1, 2 |
| `v1`, `v2` suffix | `workv1`, `workv2` | Volume 1, 2 |
| `_0001`, `_0002` | `b32839789_0001` | Part 1, 2 |
| `vol1`, `vol2` | `workvol1` | Volume 1, 2 |

### Title Variations
Search for volume indicators in titles:

```bash
ia-utils search-ia -q "title:volume" -q "Spalteholz" -m texts --has-ocr
ia-utils search-ia -q "title:vol" -q "anatomy" -m texts --has-ocr
ia-utils search-ia -q "title:part" -q "surgery" -m texts --has-ocr
```

## Finding All Volumes of a Work

### Strategy 1: Search by Author and Title
```bash
# Find all volumes of Spalteholz's atlas
ia-utils search-ia -q "Hand atlas human anatomy" --creator "Spalteholz" -m texts --has-ocr \
  -f identifier -f title -f date -f volume -s date:asc
```

### Strategy 2: Search by Identifier Pattern
If you have one volume, look for related identifiers:
```bash
# Found handatlashumananatomy1923v1, search for siblings
ia-utils search-ia -q "identifier:handatlashumananatomy1923*" -m texts
```

### Strategy 3: Check Item Metadata
Sometimes related volumes are listed in the description:
```bash
ia-utils info handatlashumananatomy1923v1 -f description
```

## Working with Individual Volumes

### Create Separate Indexes
Each volume needs its own index:

```bash
# Create indexes for each volume
ia-utils create-index handatlashumananatomy1923v1 -d ./indexes/
ia-utils create-index handatlashumananatomy1923v2 -d ./indexes/
ia-utils create-index handatlashumananatomy1923v3 -d ./indexes/
```

### Search Across Volumes
Search each index and combine results:

```bash
# Search all volumes for a term
for vol in ./indexes/handatlas*v*.sqlite; do
  echo "=== $(basename $vol) ==="
  ia-utils search-index -i "$vol" -q "nerve" -l 5
done
```

### Identify Which Volume to Use
Check the table of contents or index in volume 1 to find which volume contains your topic:

```bash
# Get TOC from volume 1
ia-utils get-text -i ./indexes/work_v1.sqlite -l 2-10

# Check index if present
ia-utils search-index -i ./indexes/work_v1.sqlite -q "index"
```

## Bound vs Unbound Editions

Some multi-volume works exist in both formats on IA:

### Separately Bound Volumes
- Each volume is a separate IA item
- Smaller file sizes
- May have different scan quality between volumes
- Example: `handatlashumananatomy1923v1`, `v2`, `v3`

### Bound-Together Editions
- All volumes in a single IA item
- Larger file size but complete
- Consistent scan quality throughout
- Example: `b31362138` (Spalteholz 3 volumes bound as one)

**To find bound editions:**
```bash
# Search for complete/bound editions
ia-utils search-ia -q "Spalteholz" -m texts --has-ocr -s downloads:desc
# Check imagecount - bound editions will have more pages
ia-utils info b31362138 -f imagecount
# Output: imagecount: 976 (all 3 volumes)
```

## Cross-Volume References

Historical texts often reference content in other volumes. When you encounter:
- "See Vol. II, p. 234"
- "Continued in Part 2"
- "Plate in Volume III"

### Resolving Cross-References
1. **Identify the target volume** from the reference
2. **Find the corresponding IA item** using search
3. **Create index if needed** for that volume
4. **Navigate to the page** using book page number:
   ```bash
   ia-utils get-url -i volume2.sqlite -b 234 --viewer
   ```

## Example: Complete Workflow

**Task**: Find all information about the femur in Spalteholz's 3-volume atlas.

```bash
# 1. Find all volumes
ia-utils search-ia -q "Spalteholz hand atlas anatomy" -m texts --has-ocr \
  --year 1920-1930 -f identifier -f title -f volume -s date:asc

# 2. Identify volumes (or find bound edition)
# Found: handatlashumananatomy1923v1, v2, v3
# Also found: b31362138 (all volumes bound together)

# 3. For efficiency, use the bound edition
ia-utils create-index b31362138 -d ./indexes/

# 4. Search for femur
ia-utils search-index -i ./indexes/spalteholz*.sqlite -q "femur"

# If using separate volumes:
# 3a. Create indexes for each
for v in 1 2 3; do
  ia-utils create-index handatlashumananatomy1923v$v -d ./indexes/
done

# 4a. Search each volume
for idx in ./indexes/hand-atlas*v*.sqlite; do
  echo "=== $idx ==="
  ia-utils search-index -i "$idx" -q "femur" -l 3
done
```

## Tips for LLMs

1. **Prefer bound editions** when available - simpler to work with, consistent quality

2. **Check imagecount** to distinguish:
   - Single volume: typically 200-600 pages
   - Bound multi-volume: typically 800+ pages

3. **Note volume in results**: When presenting findings, always indicate which volume:
   ```
   Found on page 145 (Volume 2, leaf 175)
   ```

4. **Handle missing volumes**: If only some volumes are available, inform the user:
   ```
   "Volume 2 is available on IA, but volumes 1 and 3 are not currently accessible."
   ```

5. **Cross-reference carefully**: When text says "see Vol. II", verify you have access to that volume before promising the user information.

6. **Edition consistency**: When working across volumes, try to use the same edition/year - page references may differ between editions.
