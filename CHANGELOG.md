# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases prior to 0.18.0 are recorded in the
[GitHub Releases](https://github.com/mhalle/ia-utils/releases) history.

## [0.18.1] - 2026-06-23

### Fixed

- Extended the `CAST(page_id AS INTEGER)` normalization (introduced for
  `get-text` in 0.18.0) to `search-index`, `get-page-stats`, and `get-pages`,
  so they handle older indexes that store `text_blocks.page_id` as zero-padded
  text. `search-index` now returns integer leaf numbers and resolves book page
  numbers via `page_numbers` on these indexes; `get-pages` `--all` and
  open-ended ranges compute leaf bounds correctly; and `get-page-stats` selects
  pages correctly against integer leaf ranges.

## [0.18.0] - 2026-06-23

### Added

- `get-text` now accepts `-b/--book` to select pages by printed book page
  number (single `-b 42`, range `-b 100-110`, or list `-b 1,3,5`), resolving
  each book page to its leaf via the `page_numbers` table. This brings
  `get-text` in line with `get-page`, `get-pages`, `get-url`, `ocr-page`, and
  `get-page-stats`, which already supported `-b`. Exactly one of `-l/--leaf` or
  `-b/--book` is required.

### Fixed

- `get-text` returned empty text on indexes where `text_blocks.page_id` is
  stored as zero-padded text (older index format). Page lookups now normalize
  with `CAST(page_id AS INTEGER)`, so both integer and zero-padded `page_id`
  schemas resolve correctly in page and `--blocks` modes.

[0.18.1]: https://github.com/mhalle/ia-utils/compare/v0.18.0...v0.18.1
[0.18.0]: https://github.com/mhalle/ia-utils/compare/v0.17.1...v0.18.0
