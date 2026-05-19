# Navigation Outlines (`derived_outline`)

An ia-utils index can optionally carry a `derived_outline` table: a
hierarchical outline of the document's chapters, sections, plates, or
whatever its native structure is.

The outline is a **derived** artifact, not a faithful transcription of
the printed table of contents. Entries may come from the TOC, from
per-plate caption extraction, from typographic detection in the body
text, or from manual correction. Provenance caveats live in the freeform
`notes` column.

The CLI is **deterministic plumbing only.** It loads JSON into the
table, prints what's there, and clears it. The non-deterministic step —
figuring out *what the outline should be* — happens outside ia-utils,
typically by feeding TOC page images to a vision-capable LLM.

The schema is identical to the `derived_outline` table in the sister
project **iiif-utils**, so the same JSON payload can be imported into
either CLI without modification.

## Schema

```sql
CREATE TABLE derived_outline (
  id                 INTEGER PRIMARY KEY,
  level              INTEGER NOT NULL,
  parent_id          INTEGER REFERENCES derived_outline(id),
  title              TEXT    NOT NULL,
  printed_page_start TEXT,
  printed_page_end   TEXT,
  canvas_start       INTEGER NOT NULL,
  canvas_end         INTEGER NOT NULL,
  notes              TEXT
);
CREATE INDEX ix_outline_canvas ON derived_outline(canvas_start);
CREATE INDEX ix_outline_parent ON derived_outline(parent_id);
```

| column | required | meaning |
|---|---|---|
| `id` | auto | opaque row id. |
| `level` | yes | depth in the tree, `0` for roots. Must equal the nesting depth in the import payload — redundant with the tree shape, but kept explicit so each row stands alone. |
| `parent_id` | no (NULL for roots) | navigation only. Boundaries are stored on each row, so consumers that don't need hierarchy can ignore this. |
| `title` | yes | the native heading as the work announces it — `CONTENTS`, `Inhalt`, `Chapter VI — The Spinal Cord`, `Plate XI`. No normalization. |
| `printed_page_start` / `printed_page_end` | no | printed page labels. May be integers, Roman-numeral strings, or NULL (front matter, unpaginated plates). |
| `canvas_start` / `canvas_end` | yes | the `page_numbers.leaf_num` range, **stored explicitly** — not computed at query time. |
| `notes` | no | short human-readable caveat. NULL is the common case. |

`canvas_start` / `canvas_end` index into `page_numbers.leaf_num` — the
same column ia-utils uses everywhere for physical scan order. The
column names use the IIIF "canvas" terminology so the schema is
byte-compatible with iiif-utils.

Each row is **self-contained**: its leaf range is on the row, not
inferred from neighbors. `parent_id` exists for hierarchy traversal but
is not load-bearing for ordering or boundaries.

The canonical sort is `ORDER BY id`. The importer walks the JSON tree
top-down, sqlite assigns ids in insertion order, and the validator
enforces that `canvas_start` is monotonic in id order — so id order is
reading order, with no tiebreaker needed.

## Commands

### `ia-utils outline-import <index> <payload.json>`

Bulk-load a JSON outline. Atomic — validation errors or insert failures
roll back the transaction; a partial outline is never left behind.

```bash
# normal import
ia-utils outline-import anatomicalatlasi00smit.sqlite outline.json
# → imported 122 outline entries into anatomicalatlasi00smit.sqlite

# validate without writing
ia-utils outline-import anatomicalatlasi00smit.sqlite outline.json --dry-run
# → OK (dry-run): 122 entries valid for anatomicalatlasi00smit

# overwrite an existing outline (clear-then-import in one transaction)
ia-utils outline-import anatomicalatlasi00smit.sqlite outline.json --replace
```

The payload's `"work"` field must match the index's IA `identifier`
(from `document_metadata`), falling back to the sqlite filename stem if
the metadata is absent.

**Validations enforced:**

- `payload.work` matches the index's work id.
- `entries` is a non-empty array.
- Every entry has `level`, `title`, `canvas_start`, `canvas_end`.
- `canvas_end >= canvas_start`.
- Leaf indices lie within `[0, max(page_numbers.leaf_num)]`.
- Each entry's `level` equals its nesting depth in the tree.
- Each child's `[canvas_start, canvas_end]` is within its parent's range.
- Flattened `canvas_start` values are non-decreasing.

Without `--replace`, the command refuses to import when
`derived_outline` already has rows.

### `ia-utils outline-list <index> [--format tree|table|json|jsonl|records|csv]`

Pretty-print the outline. The default `tree` format renders an indented
hierarchical view; other formats emit one row per entry for piping into
other tools.

```bash
$ ia-utils outline-list anatomicalatlasi00smit.sqlite
Front Matter  [leaves 0-10]
  Title Page pp.i  [leaf 2]
Plates pp.1-180  [leaves 11-200]
  ↳ smoke-test entry
```

Notes attached to a row appear indented underneath with a `↳` marker.

### `ia-utils outline-clear <index> [--yes]`

Delete all rows from `derived_outline` (the table itself is kept). Use
this before re-importing an outline; or just use `outline-import
--replace`, which is atomic. Other tables (`page_numbers`,
`text_blocks`, `archive_files`, …) are untouched. Confirmation is
required unless `--yes` is passed.

### `ia-utils outline-status <index> [<index> ...]`

Across one or more indices, print a one-row summary showing leaf count,
outline row count (or `—` when absent), top-level entries, max nesting
depth, and the work id. Useful for tracking outline-population progress
across a corpus.

```bash
ia-utils outline-status indexes/*.sqlite
```

`--missing-only` filters to indices that have no outline yet — the
natural batch-driver input. Pipe-friendly formats: `--format
jsonl|json|records|csv`.

## Payload format

```json
{
  "work": "anatomicalatlasi00smit",
  "entries": [
    {
      "level": 0,
      "title": "Front Matter",
      "canvas_start": 0,
      "canvas_end": 10,
      "children": [
        {
          "level": 1,
          "title": "Title Page",
          "canvas_start": 2,
          "canvas_end": 2,
          "printed_page_start": "i",
          "printed_page_end": "i"
        }
      ]
    },
    {
      "level": 0,
      "title": "Plates",
      "canvas_start": 11,
      "canvas_end": 200,
      "printed_page_start": 1,
      "printed_page_end": 180
    }
  ]
}
```

`printed_page_start`, `printed_page_end`, `notes`, and `children` are
all optional. `level` must equal the nesting depth (roots are `0`).

A machine-validatable JSON Schema lives at
[`outline-schema.json`](outline-schema.json).

### On what belongs at `level = 0`

"Level 0" means the topmost structural unit *in this document* —
whatever the work calls it. Common shapes:

- **Single-volume works:** chapters at level 0, sections at level 1.
- **Bound-together volumes:** each physical volume at level 0, chapters
  at level 1. (Page-number resolution must be volume-scoped if printed
  pagination restarts inside each volume — check
  `page_numbers.book_page_number` for duplicates.)
- **Early-modern *Liber* works:** *Liber I, II, III* at level 0,
  *Caput* at level 1.
- **Atlases with parallel sequences:** "Contents" and "List of Plates"
  as two parallel level-0 roots.

### On a synthetic "CONTENTS" / "Inhalt" root

The schema enforces that each child's `[canvas_start, canvas_end]` lies
within its parent's. A TOC-heading root cannot be parented at the TOC
pages only (e.g. leaves 12–14) while listing chapters that live at
leaves 16+ — the children would fall outside the parent. If you want
such a root, give it a range that spans all its children, and note the
TOC's actual location in `notes`. The simpler convention is to omit the
synthetic root entirely.

## On the `notes` column

`notes` is for **human-readable caveats that don't need to be queried.**
If you'd ever filter on it, that's a typed column instead.

Typical uses:

- *Why this entry exists when it isn't from the TOC* — "synthesized
  root, work has no titled heading"; "extracted from caption on leaf 47".
- *OCR / transcription corrections* — "TOC printed as `10⁰`,
  interpolated as 109".
- *Resolution offsets applied* — "printed_page resolved via −1 offset".
- *Manual edits* — "corrected title 2026-05-12 from VLM misread".

Conventions: short — one sentence per caveat, separated by `; ` when
multiple. Plain English, no codes. NULL is the common case.

## Typical workflow

1. **Identify the TOC pages.** Front matter is the usual location; for
   Continental atlases, also check back matter. The `index_metadata`
   slug and IIIF range labels can be informative.

   ```bash
   ia-utils search-index -i index.sqlite -q "contents" -l 5
   ```

2. **Fetch them at a readable resolution.** A small mosaic is a good
   first pass; full-resolution single pages for the actual parse.

   ```bash
   ia-utils get-pages -i index.sqlite -l :10 --mosaic -o overview.jpg
   ia-utils get-pages -i index.sqlite -l 8-12 -p toc/page --size large
   ```

3. **Drive the VLM** outside ia-utils. Hand it the images plus a prompt
   asking for the structured payload above. The model, the prompt, and
   the correction workflow are out of scope for this package.

4. **Import** the resulting JSON:

   ```bash
   ia-utils outline-import index.sqlite outline.json
   ```

5. **Verify:**

   ```bash
   ia-utils outline-list index.sqlite
   ```

If the VLM got something wrong, edit `outline.json` and re-run with
`--replace`. For one-off fixes, hand-SQL is fine too — the schema is
small enough that `UPDATE derived_outline SET title=… WHERE id=…` is no
more painful than editing the JSON.

## Querying

`canvas_start` / `canvas_end` are stored on every row, so typical
lookups don't need a recursive CTE:

```sql
-- Leaf range for the chapter on the spinal cord
SELECT canvas_start, canvas_end FROM derived_outline
WHERE level = 0 AND title LIKE 'The Spinal Cord%';

-- Every entry that mentions 'lymphatic'
SELECT title, canvas_start FROM derived_outline
WHERE title LIKE '%lymphatic%'
ORDER BY id;

-- Joined with page_numbers to get the printed-page range
SELECT o.title, pn_start.book_page_number, pn_end.book_page_number
FROM derived_outline o
LEFT JOIN page_numbers pn_start ON pn_start.leaf_num = o.canvas_start
LEFT JOIN page_numbers pn_end   ON pn_end.leaf_num   = o.canvas_end
WHERE o.level = 0
ORDER BY o.id;
```

A recursive CTE is only needed for tree-shaped output — see the
`outline-list` source for an example.

**Reading-order traversal.** `ORDER BY id` is canonical: `id` is
autoincremented in insertion order, the importer walks the JSON tree
top-down, and the validator enforces monotonicity of `canvas_start` — so
id order is reading order, no tiebreaker needed.
