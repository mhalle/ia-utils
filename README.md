# ia-utils

CLI tool to work with Internet Archive documents.

Utilities for building searchable SQLite catalog databases from any IA document (textbooks, manuscripts, journals, atlases, etc.) that has OCR (hOCR HTML format), and downloading/converting page images.

## Installation

```bash
uv sync
```

## Usage

```bash
uv run ia-utils --help
```

## Commands

- `create-catalog` - Build a searchable SQLite database from an IA document
- `get-page` - Download and convert a single page image
- `get-pages` - Download and convert multiple page images (batch)
- `get-pdf` - Download PDF from IA document
- `search-catalog` - Full-text search a catalog database
- `rebuild-catalog` - Rebuild text indexes in existing catalog

## Development

```bash
uv sync --dev
uv run pytest
```
