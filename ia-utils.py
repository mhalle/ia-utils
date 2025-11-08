#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "click>=8.1.0",
#     "requests>=2.31.0",
#     "sqlite-utils>=3.30.0",
#     "beautifulsoup4>=4.12.0",
#     "lxml>=4.9.0",
#     "pillow>=10.0.0",
#     "remotezip>=0.12.0",
# ]
# ///
"""
CLI tool to work with Internet Archive documents.

Utilities for building searchable SQLite catalog databases from any IA document
(textbooks, manuscripts, journals, atlases, etc.) that has OCR (hOCR HTML format),
and downloading/converting page images.

COMMANDS:
  create-catalog   Build a searchable SQLite database from an IA document
  get-page         Download and convert a single page image from IA documents
  get-pages        Download and convert multiple page images from IA documents (batch)
  search           Full-text search a catalog database
  rebuild-catalog  Rebuild text indexes in existing catalog

GLOBAL OPTIONS:
  -v, --verbose    Show detailed progress output (default: silent)

GET-PAGE COMMAND LOGIC:
  1. IDENTIFIER (positional, required):
     - IA ID: "b31362138"
     - Full URL: "https://archive.org/details/b31362138"
     - URL with page: "https://archive.org/details/b31362138/page/n404/" (sequential)
     - URL with page: "https://archive.org/details/b31362138/page/404/" (book page)

  2. PAGE NUMBER & TYPE:
     - Extract from URL if available (/page/nXXX/ or /page/XXX/)
     - Override with -n/--num-type flags if provided
     - Default to 'page' type if not specified
     Priority: Command-line flags > URL extraction > defaults

  3. CATALOG (-c, optional):
     - Speeds up book page lookups (uses cached page_numbers table)
     - Validates IA ID matches if identifier is a URL
     - If not provided, page_numbers.json downloaded on-demand for book pages

  4. OUTPUT:
     - Default: {ia_id}_{page:04d}.{format}
     - With -o: Use provided path
     - Format: Inferred from suffix (.jpg, .png, .jp2) or --format flag

Usage Examples:
    uv run ia-utils.py create-catalog IDENTIFIER
    uv run ia-utils.py create-catalog https://archive.org/details/anatomicalatlasi00smit
    uv run ia-utils.py create-catalog anatomicalatlasi00smit -a

    uv run ia-utils.py get-page anatomicalatlasi00smit -n 5 -o page.png
    uv run ia-utils.py get-page anatomicalatlasi00smit -n 0005 --num-type leaf -o page.jpg --quality 85
    uv run ia-utils.py get-page https://archive.org/details/b31362138/page/n404/ -o page.png
    uv run ia-utils.py get-page b31362138 -n 404 -c catalog.sqlite -o page.jpg

    uv run ia-utils.py -v get-page https://archive.org/details/anatomicalatlasi00smit/page/42/ --width 800 --autocontrast

    uv run ia-utils.py search catalog.sqlite "search term"
"""

import click
import sqlite_utils
import xml.etree.ElementTree as ET
import re
import sys
import json
import requests
from pathlib import Path
from datetime import datetime
from statistics import mean
from typing import Optional, Tuple, Dict, Any
from io import BytesIO

from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageOps
from remotezip import RemoteZip


def extract_ia_id(input_str: str) -> str:
    """Extract IA ID from URL or return as-is if already an ID."""
    if input_str.startswith('http'):
        # Parse URL: https://archive.org/details/IDENTIFIER
        if '/details/' in input_str:
            return input_str.split('/details/')[-1].split('/')[0]
    return input_str


def download_file(ia_id: str, filename: str, verbose: bool = True) -> bytes:
    """Download a file from Internet Archive and return bytes."""
    url = f"https://archive.org/download/{ia_id}/{filename}"

    if verbose:
        click.echo(f"   Downloading {filename}...", nl=False)

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        if verbose:
            size_mb = len(response.content) / 1024 / 1024
            click.echo(f" ✓ ({size_mb:.1f} MB)")
        return response.content
    except Exception as e:
        click.echo(f"Error downloading {filename}: {e}", err=True)
        raise


def parse_metadata(meta_bytes: bytes) -> dict:
    """Parse meta.xml bytes."""
    root = ET.fromstring(meta_bytes)
    metadata = {}
    for child in root:
        metadata[child.tag] = child.text
    return metadata


def download_json(ia_id: str, filename: str, verbose: bool = True) -> dict:
    """Download a JSON file from Internet Archive and return parsed data.

    Returns empty dict if download fails.
    """
    url = f"https://archive.org/download/{ia_id}/{filename}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        if verbose:
            click.echo(f"   Warning: Could not download {filename}: {e}", err=True)
        return {}


def parse_files(files_bytes: bytes) -> list:
    """Parse files.xml bytes."""
    root = ET.fromstring(files_bytes)
    files = []

    for file_elem in root.findall('file'):
        filename = file_elem.get('name', '')
        format_elem = file_elem.find('format')
        size_elem = file_elem.find('size')
        source = file_elem.get('source', '')
        md5 = file_elem.find('md5')
        sha1 = file_elem.find('sha1')
        crc32 = file_elem.find('crc32')

        files.append({
            'filename': filename,
            'format': format_elem.text if format_elem is not None else '',
            'size': int(size_elem.text) if size_elem is not None else 0,
            'source': source,
            'md5': md5.text if md5 is not None else '',
            'sha1': sha1.text if sha1 is not None else '',
            'crc32': crc32.text if crc32 is not None else '',
        })

    return files


def parse_bbox(title_str: str) -> Tuple[Optional[int], ...]:
    """Extract bbox coordinates from hOCR title attribute.

    Example: 'bbox 197 303 1339 379' -> (197, 303, 1339, 379)
    """
    match = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', title_str)
    if match:
        return tuple(map(int, match.groups()))
    return (None, None, None, None)


def parse_confidence(title_str: str) -> Optional[int]:
    """Extract x_wconf from title attribute.

    Example: 'x_wconf 91' -> 91
    """
    match = re.search(r'x_wconf (\d+)', title_str)
    return int(match.group(1)) if match else None


def parse_font_size(title_str: str) -> Optional[int]:
    """Extract x_fsize from title attribute.

    Example: 'x_fsize 39' -> 39
    """
    match = re.search(r'x_fsize (\d+)', title_str)
    return int(match.group(1)) if match else None


def extract_plain_text(block: Tag) -> str:
    """Extract all text content, removing HTML markup.

    Preserves word spacing and line breaks.
    """
    words = block.find_all(class_='ocrx_word')
    word_texts = [word.get_text(strip=True) for word in words]
    return ' '.join(word_texts)


def get_block_type(block: Tag) -> str:
    """Determine block type from CSS classes.

    Returns: 'ocr_par', 'ocr_caption', 'ocr_header', etc.
    """
    classes = block.get('class', [])

    # Handle both string (XML parser) and list (HTML parser)
    if isinstance(classes, str):
        classes = classes.split()

    ocr_classes = [c for c in classes if c.startswith('ocr_')]
    return ocr_classes[0] if ocr_classes else 'unknown'


def sort_blocks_by_position(blocks: list) -> list:
    """Sort blocks by visual position (top-to-bottom, left-to-right).

    Uses bbox y0 (top edge) as primary sort key.
    """
    def get_position(block):
        title = block.get('title', '')
        bbox = parse_bbox(title)
        return (bbox[1] or 0, bbox[0] or 0)  # (y0, x0)

    return sorted(blocks, key=get_position)


def extract_page_id(page: Tag) -> str:
    """Extract page ID from hOCR page element.

    Example: 'page_000022' -> '000022'
    """
    page_id = page.get('id', '')
    match = re.search(r'page_(\d+)', page_id)
    return match.group(1) if match else ''


def extract_parent_carea_id(block: Tag) -> Optional[str]:
    """Find parent column area ID (carea)."""
    parent = block.parent
    while parent and parent.name != 'div':
        parent = parent.parent
    if parent and 'ocr_carea' in (parent.get('class') or []):
        return parent.get('id')
    return None


def parse_hocr(hocr_bytes: bytes) -> list:
    """Parse hOCR HTML bytes and extract text blocks using BeautifulSoup.

    Returns a list of block dictionaries with proper semantic structure.
    """
    click.echo("   Parsing hOCR...", nl=False)

    hocr_content = hocr_bytes.decode('utf-8')
    soup = BeautifulSoup(hocr_content, 'xml')

    # Get all pages
    pages = soup.find_all(class_='ocr_page')
    total_blocks = 0
    blocks_list = []

    # Process each page
    for page_idx, page in enumerate(pages, 1):
        page_id = extract_page_id(page)

        # Get all text block types
        blocks = (
            page.find_all(class_='ocr_par') +
            page.find_all(class_='ocr_caption') +
            page.find_all(class_='ocr_header') +
            page.find_all(class_='ocr_textfloat')
        )

        # Sort blocks by position
        blocks = sort_blocks_by_position(blocks)

        # Process each block
        for block_number, block in enumerate(blocks):
            # Extract basic attributes
            hocr_id = block.get('id', '')
            block_type = get_block_type(block)
            language = block.get('lang') or block.get('xml:lang')
            text_direction = block.get('dir', 'ltr')

            # Parse bounding box
            title = block.get('title', '')
            bbox = parse_bbox(title)

            # Extract plain text
            text = extract_plain_text(block)

            # Only process blocks with actual text
            if not text.strip():
                continue

            # Find parent column area
            parent_carea_id = extract_parent_carea_id(block)

            # Compute statistics
            lines = block.find_all(class_='ocr_line')
            line_count = len(lines)

            words = block.find_all(class_='ocrx_word')
            word_count = len(words)

            # Average confidence from word-level x_wconf
            confidences = [
                parse_confidence(word.get('title', ''))
                for word in words
            ]
            confidences = [c for c in confidences if c is not None]
            avg_confidence = mean(confidences) if confidences else None

            # Average font size from word-level x_fsize
            font_sizes = [
                parse_font_size(word.get('title', ''))
                for word in words
            ]
            font_sizes = [f for f in font_sizes if f is not None]
            avg_font_size = mean(font_sizes) if font_sizes else None

            blocks_list.append({
                'page_id': page_id,
                'block_number': block_number,
                'hocr_id': hocr_id,
                'block_type': block_type,
                'language': language,
                'text_direction': text_direction,
                'bbox_x0': bbox[0],
                'bbox_y0': bbox[1],
                'bbox_x1': bbox[2],
                'bbox_y1': bbox[3],
                'text': text,
                'line_count': line_count,
                'word_count': word_count,
                'avg_confidence': avg_confidence,
                'avg_font_size': avg_font_size,
                'parent_carea_id': parent_carea_id,
            })
            total_blocks += 1

    click.echo(f" ✓ ({total_blocks} blocks)")
    return blocks_list


def generate_slug(metadata: dict, ia_id: str) -> str:
    """Generate a human-readable slug from metadata: author-title-date-edition_ia_id.

    Format:
    - First author name (last name)
    - First 4 significant words from title (noise words removed)
    - Publication year
    - Edition info (if present)
    - IA ID as unique identifier
    """
    # Extract first author
    creators = metadata.get('creator', 'unknown')
    if isinstance(creators, str):
        # Handle "Last Name, First Name" format - take first author, last name only
        first_creator = creators.split(';')[0].split(',')[0].strip().lower()
        author = re.sub(r'[^a-z0-9]', '', first_creator)
    else:
        author = 'unknown'

    # Extract and clean title - keep first 4 significant words
    title = metadata.get('title', 'document').lower()
    noise_words = {'the', 'of', 'a', 'an', 'and', 'or', 'in', 'for', 'to', 'with', 'by', 'on', 'at'}

    # Remove punctuation and split
    title_cleaned = re.sub(r'[^a-z0-9\s]', '', title)
    words = [w for w in title_cleaned.split() if w and w not in noise_words]
    title_part = '-'.join(words[:4])  # First 4 significant words

    # Extract publication year
    date = metadata.get('date', '')
    year = date[:4] if date and len(date) >= 4 else ''

    # Check for edition
    edition = metadata.get('edition', '')
    if edition:
        edition = re.sub(r'[^a-z0-9]', '', edition.lower())

    # Combine parts
    slug_parts = [author, title_part, year]
    if edition:
        slug_parts.append(edition)

    human_readable = '-'.join(p for p in slug_parts if p)
    slug = f"{human_readable}_{ia_id}"

    return slug


def build_text_blocks(db: sqlite_utils.Database, ia_id: str, hocr_filename: str):
    """Download hOCR file, parse it, and populate text_blocks table."""
    click.echo("   Downloading hOCR...", nl=False)
    hocr_bytes = download_file(ia_id, hocr_filename, verbose=False)
    click.echo(" ✓")

    blocks_list = parse_hocr(hocr_bytes)

    click.echo("   Inserting into text_blocks...", nl=False)
    db['text_blocks'].drop(ignore=True)
    db['text_blocks'].insert_all(
        blocks_list,
        pk='hocr_id',
        replace=True,
    )
    click.echo(" ✓")

    return len(blocks_list)


def normalize_page_number(page_input: str) -> int:
    """Convert page input (with or without leading zeros) to integer.

    Examples:
        '5' -> 5
        '0005' -> 5
        '001' -> 1
    """
    return int(page_input)


def extract_ia_id_and_page(input_str: str) -> Tuple[str, Optional[int], Optional[str]]:
    """Extract IA ID and optional page number from URL or ID string.

    Handles formats like:
    - https://archive.org/details/b31362138/page/404/ (book page, requires catalog)
    - https://archive.org/details/b31362138/page/n404/ (sequential page, 0-origin)
    - https://archive.org/details/anatomicalatlasi00smit
    - anatomicalatlasi00smit

    Returns:
        Tuple of (ia_id, page_number or None, page_type or None)
        page_type is 'page' for sequential (from /page/nXXX/) or 'book' for book pages (from /page/XXX/)
    """
    ia_id = extract_ia_id(input_str)  # Use existing function for IA ID extraction

    # Check for page info in URL
    page_num = None
    page_type = None
    if '/page/' in input_str:
        try:
            # Format: /page/404/ or /page/n404/
            page_part = input_str.split('/page/')[-1].rstrip('/')
            # Check if 'n' prefix is present (sequential page)
            if page_part.startswith('n'):
                page_type = 'page'
                page_part = page_part[1:]
            else:
                page_type = 'book'
            page_num = int(page_part)
        except (ValueError, IndexError):
            pass

    return ia_id, page_num, page_type


def get_page_number_for_jp2(page_num: int, page_type: str, ia_id: str = None, db: sqlite_utils.Database = None) -> int:
    """Convert from leaf/book page to sequential page number for jp2 files.

    JP2 files in the archive are numbered sequentially (1-indexed): _0001.jp2, _0002.jp2, etc.

    Args:
        page_num: The page number in the specified format
        page_type: 'page' (sequential), 'leaf' (physical page), or 'book' (book page number)
        ia_id: Internet Archive identifier (needed for book/leaf lookups)
        db: Optional sqlite_utils Database object (uses page_numbers table if available)

    Returns:
        The sequential page number (1-indexed) for the jp2 filename
    """
    if page_type == 'page':
        # 'page' type is already the sequential page number
        return page_num

    elif page_type == 'leaf':
        # leaf number maps directly to sequential page number
        return page_num

    elif page_type == 'book':
        # 'book' page numbers need to be looked up in page_numbers table
        if db:
            try:
                result = db.execute(
                    "SELECT leaf_num FROM page_numbers WHERE book_page_number = ?",
                    [str(page_num)]
                ).fetchone()
                if result:
                    return result[0]
                else:
                    raise ValueError(f"Book page number {page_num} not found in page_numbers table")
            except Exception as e:
                raise ValueError(f"Could not look up book page number {page_num}: {e}")
        elif ia_id:
            # Download page_numbers.json on the fly
            try:
                page_data = download_json(ia_id, f"{ia_id}_page_numbers.json", verbose=False)
                if 'pages' in page_data:
                    for page_entry in page_data['pages']:
                        if page_entry.get('pageNumber') == str(page_num):
                            return page_entry['leafNum']
                raise ValueError(f"Book page number {page_num} not found in page_numbers.json")
            except Exception as e:
                raise ValueError(f"Could not look up book page number {page_num}: {e}")
        else:
            raise ValueError("Book page lookup requires either catalog database or IA ID")

    else:
        raise ValueError(f"Unknown page_type: {page_type}")


def parse_page_range(range_str: str) -> list:
    """Parse page range string into list of page numbers.

    Supports formats:
    - Single page: '42'
    - Range: '1-7' (inclusive)
    - Comma-separated: '1,3,5'
    - Mixed: '1-7,21,25,45-50'

    Returns:
        Sorted list of unique integers

    Raises:
        ValueError: If format is invalid
    """
    pages = set()

    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue

        if '-' in part:
            # Range format: "1-7"
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                if start > end:
                    raise ValueError(f"Invalid range: {start}-{end} (start > end)")
                pages.update(range(start, end + 1))
            except ValueError as e:
                raise ValueError(f"Invalid range format '{part}': {e}")
        else:
            # Single page
            try:
                pages.add(int(part))
            except ValueError:
                raise ValueError(f"Invalid page number '{part}'")

    if not pages:
        raise ValueError("No valid page numbers parsed")

    return sorted(list(pages))


def generate_page_filename(prefix: str, page_num: int, output_format: str) -> str:
    """Generate output filename for a single page in batch operation.

    Format: {prefix}_{page:04d}.{format}

    Args:
        prefix: Output prefix (can include directory path)
        page_num: Page number to format
        output_format: File format (jpg, png, jp2)

    Returns:
        Formatted filename
    """
    # Ensure format doesn't have leading dot
    fmt = output_format.lstrip('.')
    return f"{prefix}_{page_num:04d}.{fmt}"


def download_and_convert_page(ia_id: str, page_num: int, output_path: Path,
                              width: Optional[int] = None,
                              quality: Optional[int] = None,
                              output_format: str = 'jp2',
                              autocontrast: bool = False,
                              cutoff: Optional[int] = None,
                              preserve_tone: bool = False,
                              verbose: bool = False) -> None:
    """Download a page image from IA jp2.zip and optionally convert/resample.

    Args:
        ia_id: Internet Archive identifier
        page_num: Sequential page number (1-indexed)
        output_path: Path to write output file
        width: Optional width for resampling (maintains aspect ratio)
        quality: JPEG quality (1-95), only used for JPEG output
        output_format: Output format ('jp2', 'jpg', 'png')
        autocontrast: Whether to apply autocontrast enhancement
        cutoff: Autocontrast cutoff percentage (0-100, enables autocontrast if set)
        preserve_tone: Whether to preserve tone in autocontrast (enables autocontrast)
        verbose: Whether to print detailed logging messages
    """
    # Format page number as 4-digit zero-padded for jp2 archive
    jp2_page_num = f"{page_num:04d}"
    jp2_filename = f"{ia_id}_{jp2_page_num}.jp2"
    # Files are stored in subdirectory {ia_id}_jp2/
    jp2_path_in_zip = f"{ia_id}_jp2/{jp2_filename}"

    # IA jp2.zip URL
    zip_url = f"https://archive.org/download/{ia_id}/{ia_id}_jp2.zip"

    if verbose:
        click.echo(f"   Downloading {jp2_filename}...", nl=False)

    try:
        # Use remotezip to fetch just this one file
        with RemoteZip(zip_url) as rz:
            # Check if file exists in zip (try both with and without subdirectory)
            file_in_zip = None
            if jp2_path_in_zip in rz.namelist():
                file_in_zip = jp2_path_in_zip
            elif jp2_filename in rz.namelist():
                file_in_zip = jp2_filename

            if not file_in_zip:
                if verbose:
                    click.echo(f" ✗")
                raise FileNotFoundError(f"Page {page_num} ({jp2_filename}) not found in archive")

            # Read the jp2 file into memory
            jp2_data = rz.read(file_in_zip)

        if verbose:
            size_mb = len(jp2_data) / 1024 / 1024
            click.echo(f" ✓ ({size_mb:.1f} MB)")

        # Open image
        if verbose:
            click.echo(f"   Processing image...", nl=False)
        img = Image.open(BytesIO(jp2_data))

        # Resample if width specified
        if width:
            aspect_ratio = img.height / img.width
            new_height = int(width * aspect_ratio)
            img = img.resize((width, new_height), Image.Resampling.LANCZOS)

        # Apply autocontrast if requested or if options were explicitly set
        should_apply_autocontrast = autocontrast or cutoff is not None or preserve_tone
        if should_apply_autocontrast:
            ac_kwargs = {}
            # Use specified cutoff, or default to 2 if autocontrast is enabled but no cutoff specified
            if cutoff is not None:
                ac_kwargs['cutoff'] = cutoff
            else:
                ac_kwargs['cutoff'] = 2
            img = ImageOps.autocontrast(img, **ac_kwargs)

        # Convert format if needed
        save_kwargs = {}
        save_format = output_format.upper()

        if output_format.lower() == 'jpg':
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background

            if quality:
                save_kwargs['quality'] = quality

            save_format = 'JPEG'

        # Save output
        img.save(output_path, format=save_format, **save_kwargs)
        if verbose:
            click.echo(f" ✓")

    except Exception as e:
        click.echo(f" ✗ Error: {e}", err=True)
        raise


def batch_download_pages(ia_id: str, pages: list, prefix: str,
                         width: Optional[int] = None,
                         quality: Optional[int] = None,
                         output_format: str = 'jp2',
                         autocontrast: bool = False,
                         cutoff: Optional[int] = None,
                         preserve_tone: bool = False,
                         num_type: str = 'page',
                         db: sqlite_utils.Database = None,
                         verbose: bool = False,
                         skip_existing: bool = False) -> Tuple[int, int]:
    """Download and convert multiple pages from Internet Archive.

    Args:
        ia_id: Internet Archive identifier
        pages: List of page numbers to download
        prefix: Output filename prefix (can include directory path)
        width: Optional width for resampling
        quality: JPEG quality (1-95)
        output_format: Output format (jp2, jpg, png)
        autocontrast: Enable autocontrast
        cutoff: Autocontrast cutoff (0-100)
        preserve_tone: Preserve tone in autocontrast
        num_type: Page number type ('page', 'leaf', 'book')
        db: Optional database for page number lookups
        verbose: Print progress details
        skip_existing: Skip pages that already exist

    Returns:
        Tuple of (successful_count, failed_count)
    """
    successful = 0
    failed = 0
    total = len(pages)

    if verbose:
        click.echo(f"\nDownloading {total} pages...")

    for idx, page_num in enumerate(pages, 1):
        try:
            # Convert to sequential page number if needed
            sequential_page = get_page_number_for_jp2(page_num, num_type, ia_id=ia_id, db=db)

            # Generate output filename
            output_filename = generate_page_filename(prefix, page_num, output_format)
            output_path = Path(output_filename)

            # Check if file exists and skip if requested
            if skip_existing and output_path.exists():
                if verbose:
                    click.echo(f"  [{idx}/{total}] Skipping {output_path.name} (exists)")
                successful += 1
                continue

            if verbose:
                click.echo(f"  [{idx}/{total}] Downloading page {page_num}...", nl=False)

            # Download and convert
            download_and_convert_page(
                ia_id,
                sequential_page,
                output_path,
                width=width,
                quality=quality,
                output_format=output_format,
                autocontrast=autocontrast,
                cutoff=cutoff,
                preserve_tone=preserve_tone,
                verbose=False  # We handle verbose output here
            )

            if verbose:
                click.echo(f" ✓ ({output_path.name})")

            successful += 1

        except Exception as e:
            if verbose:
                click.echo(f" ✗ Error: {e}", err=True)
            else:
                click.echo(f"Error downloading page {page_num}: {e}", err=True)
            failed += 1

    return successful, failed


def build_fts_indexes(db: sqlite_utils.Database):
    """Build FTS indexes for text_blocks and pages."""
    # === BLOCK-LEVEL FTS INDEX ===
    db.executescript("""
        DROP TRIGGER IF EXISTS text_blocks_ai;
        DROP TRIGGER IF EXISTS text_blocks_ad;
        DROP TRIGGER IF EXISTS text_blocks_au;
        DROP TABLE IF EXISTS text_blocks_fts;
    """)
    db['text_blocks'].enable_fts(['text'], create_triggers=True)

    # === PAGE-LEVEL FTS INDEX ===
    db.executescript("""
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_insert;
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_update;
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_delete;
        DROP TABLE IF EXISTS pages_fts;

        CREATE VIRTUAL TABLE pages_fts USING fts5(
            page_text,
            page_id UNINDEXED
        );

        INSERT INTO pages_fts(rowid, page_text, page_id)
        SELECT
            ROW_NUMBER() OVER (ORDER BY page_id),
            group_concat(text, ' '),
            page_id
        FROM text_blocks
        GROUP BY page_id;

        CREATE TRIGGER rebuild_pages_fts_after_insert AFTER INSERT ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;

        CREATE TRIGGER rebuild_pages_fts_after_update AFTER UPDATE ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;

        CREATE TRIGGER rebuild_pages_fts_after_delete AFTER DELETE ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;
    """)


def build_database(ia_id: str, output_path, slug: str, metadata: dict, files: list, blocks_list: list, page_numbers_data: dict = None):
    """Build catalog SQLite database using sqlite-utils with proper hOCR structure."""
    output_path = Path(output_path)
    click.echo(f"\n   Building database: {output_path.name}")

    db = sqlite_utils.Database(output_path)

    # No preprocessing needed - text_blocks is now normalized
    # leaf_num and book_page_number will be in page_numbers table
    # ia_viewer_url can be generated on-the-fly from ia_identifier + page_id

    # === TABLE 1: DOCUMENT METADATA ===
    click.echo("     Creating document_metadata...", nl=False)

    # Extract creators
    creators = []
    for key, value in metadata.items():
        if key == 'creator' and value:
            creators.append(value)

    creator_primary = creators[0] if creators else ''
    creator_secondary = creators[1] if len(creators) > 1 else ''

    metadata_record = {
        'slug': slug,
        'ia_identifier': ia_id,
        'title': metadata.get('title', ''),
        'creator_primary': creator_primary,
        'creator_secondary': creator_secondary,
        'publisher': metadata.get('publisher', ''),
        'publication_date': metadata.get('date', ''),
        'page_count': int(metadata.get('imagecount', 0)) if metadata.get('imagecount', '').isdigit() else 0,
        'language': metadata.get('language', 'eng'),
        'ark_identifier': metadata.get('identifier-ark', ''),
        'oclc_id': metadata.get('oclc-id', ''),
        'openlibrary_edition': metadata.get('openlibrary_edition', ''),
        'openlibrary_work': metadata.get('openlibrary_work', ''),
        'scan_quality_ppi': int(metadata.get('ppi', 400)) if metadata.get('ppi', '').isdigit() else 400,
        'scan_camera': metadata.get('camera', ''),
        'scan_date': metadata.get('scandate', ''),
        'collection': metadata.get('collection', ''),
        'description': metadata.get('description', ''),
        'created_at': datetime.now().isoformat(),
    }

    db['document_metadata'].insert(metadata_record, pk='id', replace=True)
    click.echo(" ✓")

    # === TABLE 2: ARCHIVE FILES ===
    click.echo("     Creating archive_files...", nl=False)

    files_records = []
    for file_info in files:
        files_records.append({
            'document_id': 1,
            'filename': file_info['filename'],
            'format': file_info['format'],
            'size_bytes': file_info['size'],
            'source_type': file_info['source'],
            'md5_checksum': file_info['md5'],
            'sha1_checksum': file_info['sha1'],
            'crc32_checksum': file_info['crc32'],
            'download_url': f'https://archive.org/download/{ia_id}/{file_info["filename"]}',
            'created_at': datetime.now().isoformat(),
        })

    db['archive_files'].insert_all(files_records, foreign_keys=[('document_id', 'document_metadata', 'id')])
    click.echo(f" ✓ ({len(files)} files)")

    # === TABLE 3: TEXT BLOCKS ===
    click.echo("     Creating text_blocks...", nl=False)

    db['text_blocks'].insert_all(
        blocks_list,
        pk='hocr_id',
        replace=True,
    )
    click.echo(f" ✓ ({len(blocks_list)} blocks)")

    # === TABLE 4: PAGE NUMBERS (MAPPING) ===
    if page_numbers_data and 'pages' in page_numbers_data:
        click.echo("     Creating page_numbers...", nl=False)

        page_records = []
        for page_info in page_numbers_data['pages']:
            page_records.append({
                'leaf_num': page_info['leafNum'],
                'book_page_number': page_info.get('pageNumber', ''),
                'confidence': page_info.get('confidence'),
                'pageProb': page_info.get('pageProb'),
                'wordConf': page_info.get('wordConf'),
            })

        db['page_numbers'].insert_all(
            page_records,
            pk='leaf_num',
            replace=True,
        )
        click.echo(f" ✓ ({len(page_records)} page mappings)")

    # === TABLE 5: INDEXES ===
    click.echo("     Creating indexes...", nl=False)

    db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_page ON text_blocks(page_id);
        CREATE INDEX IF NOT EXISTS idx_block_type ON text_blocks(block_type);
        CREATE INDEX IF NOT EXISTS idx_language ON text_blocks(language);
        CREATE INDEX IF NOT EXISTS idx_confidence ON text_blocks(avg_confidence);
        CREATE INDEX IF NOT EXISTS idx_font_size ON text_blocks(avg_font_size);
    """)
    click.echo(" ✓")

    # === TABLES 6-7: FTS INDEXES ===
    click.echo("     Creating FTS indexes...", nl=False)
    build_fts_indexes(db)
    click.echo(" ✓")

    # === STATISTICS ===
    blocks_count = db['text_blocks'].count
    pages_count = db.execute('SELECT COUNT(DISTINCT page_id) FROM text_blocks').fetchone()[0]
    avg_conf_result = db.execute('SELECT AVG(avg_confidence) FROM text_blocks').fetchone()[0]
    avg_conf = avg_conf_result if avg_conf_result else 0
    avg_words = db.execute('SELECT AVG(word_count) FROM text_blocks').fetchone()[0]

    size_mb = output_path.stat().st_size / 1024 / 1024

    click.echo(f"\n   Database: {output_path.name}")
    click.echo(f"   Size: {size_mb:.1f} MB")
    click.echo(f"   Records: {blocks_count} text blocks across {pages_count} pages")
    click.echo(f"   Average words per block: {avg_words:.1f}" if avg_words else "   Average words per block: N/A")
    click.echo(f"   OCR Quality: {avg_conf:.0f}% average confidence")

    # Block type breakdown
    click.echo("\n   Block types:")
    type_stats = list(db.execute("""
        SELECT block_type, COUNT(*) as count
        FROM text_blocks
        GROUP BY block_type
        ORDER BY count DESC
    """))

    for row in type_stats:
        click.echo(f"     {row[0]}: {row[1]}")

    # Language breakdown
    lang_stats = list(db.execute("""
        SELECT language, COUNT(*) as count
        FROM text_blocks
        WHERE language IS NOT NULL
        GROUP BY language
        ORDER BY count DESC
    """))

    if lang_stats:
        click.echo("\n   Languages:")
        for row in lang_stats:
            click.echo(f"     {row[0]}: {row[1]}")

    return output_path


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Build and manage Internet Archive document catalogs."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


@cli.command()
@click.argument('identifier')
@click.option('-h', '--human', 'human_filename', is_flag=True, help='Use human-readable slug as filename')
@click.option('-a', '--auto', 'auto_slug', is_flag=True, help='Auto-generate slug non-interactively')
@click.option('-o', '--slug', type=str, help='Set custom slug')
@click.pass_context
def create_catalog(ctx, identifier, human_filename, auto_slug, slug):
    """Create a catalog database from an Internet Archive document.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    FILENAME MODES:
    - No flags: {id}.sqlite, interactive slug
    - -h: {human-readable-slug}.sqlite, auto-generated slug
    - -a: {id}.sqlite, auto-generated slug
    - -o custom: {id}.sqlite, custom slug
    """
    verbose = ctx.obj.get('verbose', False)
    ia_id = extract_ia_id(identifier)

    # Auto-slug when not verbose
    if not verbose:
        auto_slug = True

    # Show header when verbose
    if verbose:
        click.echo(f"\nBuilding catalog for: {ia_id}")
        click.echo("=" * 70)

    # Download files (into memory)
    if verbose:
        click.echo("\n1. Downloading files from Internet Archive...")

    try:
        meta_bytes = download_file(ia_id, f"{ia_id}_meta.xml", verbose=verbose)
        files_bytes = download_file(ia_id, f"{ia_id}_files.xml", verbose=verbose)
        hocr_bytes = download_file(ia_id, f"{ia_id}_hocr.html", verbose=verbose)
    except Exception:
        sys.exit(1)

    # Try to download page numbers mapping
    if verbose:
        click.echo("   Downloading page numbers mapping...", nl=False)
    page_numbers_data = download_json(ia_id, f"{ia_id}_page_numbers.json", verbose=verbose)
    if verbose:
        if page_numbers_data and 'pages' in page_numbers_data:
            click.echo(f" ✓ ({len(page_numbers_data['pages'])} pages)")
        else:
            click.echo(" (not available)")

    # Parse files
    if verbose:
        click.echo("\n2. Parsing source files...")

    metadata = parse_metadata(meta_bytes)
    if verbose:
        click.echo(f"   Title: {metadata.get('title', 'Unknown')}")

    files = parse_files(files_bytes)
    if verbose:
        click.echo(f"   ✓ {len(files)} file formats")

    blocks_list = parse_hocr(hocr_bytes)
    pages_set = set(block['page_id'] for block in blocks_list)
    if verbose:
        click.echo(f"   ✓ {len(pages_set)} pages")

    # Determine slug and output filename
    if verbose:
        click.echo("\n3. Determining slug...")

    if slug:
        # User specified slug directly with -o
        final_slug = slug
        if verbose:
            click.echo(f"   Using provided slug: {final_slug}")
    elif auto_slug or human_filename:
        # Auto-generate without interaction
        final_slug = generate_slug(metadata, ia_id)
        if verbose:
            click.echo(f"   Auto-generated slug: {final_slug}")
    else:
        # Interactive mode (default)
        suggested_slug = generate_slug(metadata, ia_id)
        click.echo(f"   Suggested slug: {suggested_slug}")
        final_slug = click.prompt("   Enter slug (or press Enter to accept)", default=suggested_slug)

    # Determine output filename based on flags
    if human_filename:
        # Use human-readable slug as filename
        output_filename = f"{final_slug}.sqlite"
    else:
        # Use just the IA ID as filename (for all other modes)
        output_filename = f"{ia_id}.sqlite"

    output_path = Path.cwd() / output_filename

    if verbose:
        click.echo(f"\n4. Building database...")

    build_database(ia_id, output_path, final_slug, metadata, files, blocks_list, page_numbers_data)

    if verbose:
        click.echo("\n" + "=" * 70)
        click.echo(f"✓ Database created: {output_path}")
        click.echo(f"✓ Slug: {final_slug}")
        click.echo("=" * 70)
    else:
        click.echo(output_path)


@cli.command()
@click.argument('identifier', required=False)
@click.option('-c', '--catalog', type=click.Path(exists=True), help='Load IA ID from catalog database')
@click.option('-a', '--auto', 'auto_filename', is_flag=True, help='Auto-generate filename from metadata')
@click.option('-o', '--output', type=str, help='Set custom output filename')
@click.pass_context
def get_pdf(ctx, identifier, catalog, auto_filename, output):
    """Download PDF from Internet Archive document.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    Alternatively, use -c to load IA ID from a catalog database:
    - get-pdf -c catalog.sqlite

    FILENAME MODES:
    - No flags: {id}.pdf
    - -a: {slug}.pdf (from database metadata or auto-generated)
    - -o custom: custom.pdf

    Use -v/--verbose for detailed output (global flag).
    """
    verbose = ctx.obj.get('verbose', False)

    # Determine IA ID from either identifier arg or catalog database
    if catalog:
        if identifier:
            click.echo("Error: Cannot specify both IDENTIFIER and -c/--catalog", err=True)
            sys.exit(1)

        # Load IA ID from catalog database
        if verbose:
            click.echo(f"Loading IA ID from catalog: {catalog}")

        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                click.echo("Error: No metadata found in catalog database", err=True)
                sys.exit(1)
            ia_id = metadata[0]['ia_identifier']
            slug = metadata[0].get('slug', '')
        except Exception as e:
            click.echo(f"Error reading catalog database: {e}", err=True)
            sys.exit(1)
    else:
        if not identifier:
            click.echo("Error: Must provide either IDENTIFIER or -c/--catalog", err=True)
            sys.exit(1)

        ia_id = extract_ia_id(identifier)
        slug = None

    if verbose:
        click.echo(f"\nDownloading PDF for: {ia_id}")
        click.echo("=" * 70)

    # Download PDF
    pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"

    if verbose:
        click.echo(f"\n1. Downloading PDF...")
        click.echo(f"   URL: {pdf_url}", nl=False)

    try:
        response = requests.get(pdf_url, timeout=60)
        response.raise_for_status()
        pdf_bytes = response.content
        size_mb = len(pdf_bytes) / 1024 / 1024

        if verbose:
            click.echo(f" ✓ ({size_mb:.1f} MB)")
    except Exception as e:
        if verbose:
            click.echo(f" ✗ Error: {e}", err=True)
        else:
            click.echo(f"Error downloading PDF: {e}", err=True)
        sys.exit(1)

    # Determine output filename
    if output:
        # Custom filename
        output_filename = output
        if verbose:
            click.echo(f"\n2. Using custom filename: {output_filename}")
    elif auto_filename:
        # Auto-generate from slug
        if slug:
            output_filename = f"{slug}.pdf"
            if verbose:
                click.echo(f"\n2. Auto-generated filename: {output_filename}")
        else:
            output_filename = f"{ia_id}.pdf"
            if verbose:
                click.echo(f"\n2. Auto-generated filename (from ID): {output_filename}")
    else:
        # Default: use IA ID
        output_filename = f"{ia_id}.pdf"
        if verbose:
            click.echo(f"\n2. Using filename: {output_filename}")

    # Write PDF to file
    output_path = Path.cwd() / output_filename

    try:
        output_path.write_bytes(pdf_bytes)
        if verbose:
            click.echo(f"\n" + "=" * 70)
            click.echo(f"✓ PDF saved: {output_path}")
            click.echo("=" * 70)
        else:
            click.echo(output_path)
    except Exception as e:
        if verbose:
            click.echo(f"Error writing PDF: {e}", err=True)
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('catalog', type=click.Path(exists=True))
@click.argument('search_string')
@click.option('--limit', type=int, default=10, help='Maximum results to return')
@click.option('--type', 'block_type', type=str, help='Filter by block type')
@click.option('--page', type=str, help='Filter by book page number')
def search(catalog, search_string, limit, block_type, page):
    """Search catalog database using FTS on OCR text.

    Returns matching text blocks with their viewer URLs.

    Examples:
        ia-utils search catalog.sqlite "anatomical structures"
        ia-utils search catalog.sqlite "brain" --limit 20
        ia-utils search catalog.sqlite "heart" --type ocr_par
        ia-utils search catalog.sqlite "vein" --page "42"
    """
    try:
        db = sqlite_utils.Database(catalog)
    except Exception as e:
        click.echo(f"Error opening catalog: {e}", err=True)
        sys.exit(1)

    # Build FTS query using page-level search with block density ranking
    try:
        # Get document metadata for building viewer URLs
        doc_meta = list(db['document_metadata'].rows_where(limit=1))[0]
        ia_id = doc_meta['ia_identifier']

        # Query pages_fts for page-level results, join to text_blocks for block count and leaf_num
        query = """
            SELECT DISTINCT
                tb.page_id,
                pn.leaf_num,
                COUNT(DISTINCT fbf.rowid) as match_count,
                pages_fts.rank
            FROM pages_fts
            JOIN text_blocks tb ON pages_fts.page_id = tb.page_id
            LEFT JOIN page_numbers pn ON pn.leaf_num = CAST(tb.page_id AS INTEGER) + 1
            LEFT JOIN text_blocks_fts fbf ON tb.rowid = fbf.rowid AND fbf.text MATCH ?
            WHERE pages_fts MATCH ?
        """
        params = [search_string, search_string]

        # Add optional filters on text_blocks
        if block_type:
            query += " AND tb.block_type = ?"
            params.append(block_type)

        if page:
            query += " AND pn.book_page_number = ?"
            params.append(page)

        # Group by page and order by match density (block count), then by FTS rank
        query += """
            GROUP BY pages_fts.page_id
            ORDER BY match_count DESC, pages_fts.rank DESC
            LIMIT ?
        """
        params.append(limit)

        results = list(db.execute(query, params))

        if not results:
            click.echo(f"No results found for: {search_string}", err=True)
            sys.exit(1)

        # Output results as JSON array
        results_json = []
        for row in results:
            page_id = row[0]
            leaf_num = row[1]
            match_count = row[2]
            rank = row[3]
            viewer_url = f"https://archive.org/details/{ia_id}/page/n{page_id}/"

            result_obj = {
                "page_id": page_id,
                "leaf_num": leaf_num,
                "match_count": match_count,
                "rank": rank,
                "viewer_url": viewer_url
            }
            results_json.append(result_obj)

        click.echo(json.dumps(results_json, indent=2))

    except Exception as e:
        click.echo(f"Search error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('catalog', type=click.Path(exists=True))
def rebuild_catalog(catalog):
    """Rebuild text_blocks and FTS indexes in an existing catalog database.

    Unconditionally rebuilds text_blocks from the source hOCR file (downloaded from
    Internet Archive), then rebuilds text_blocks_fts and pages_fts indexes without
    modifying other tables (document_metadata, archive_files, figures, subsections, etc.).

    This is useful after manual edits or schema updates.

    Example:
        ia-utils rebuild-catalog b31362138.sqlite
    """
    try:
        db = sqlite_utils.Database(catalog)
    except Exception as e:
        click.echo(f"Error opening catalog: {e}", err=True)
        sys.exit(1)

    # Verify required tables exist
    try:
        tables = {t.name for t in db.tables}
        if 'document_metadata' not in tables:
            click.echo("Error: catalog must have document_metadata table", err=True)
            sys.exit(1)
        if 'archive_files' not in tables:
            click.echo("Error: catalog must have archive_files table", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"Error verifying catalog structure: {e}", err=True)
        sys.exit(1)

    # Get document metadata
    try:
        doc_meta = list(db['document_metadata'].rows_where(limit=1))[0]
        ia_id = doc_meta['ia_identifier']
    except Exception as e:
        click.echo(f"Error reading document_metadata: {e}", err=True)
        sys.exit(1)

    # Find hOCR file in archive_files
    try:
        hocr_file = list(db.execute(
            "SELECT filename FROM archive_files WHERE filename LIKE ?",
            [f"{ia_id}_hocr.html"]
        ).fetchall())
        if not hocr_file:
            click.echo(f"Error: cannot find hOCR file for {ia_id}", err=True)
            sys.exit(1)
        hocr_filename = hocr_file[0][0]
    except Exception as e:
        click.echo(f"Error looking up hOCR file: {e}", err=True)
        sys.exit(1)

    click.echo(f"Rebuilding catalog: {catalog}")
    click.echo("=" * 70)

    try:
        click.echo("\n1. Building text_blocks...")
        build_text_blocks(db, ia_id, hocr_filename)

        click.echo("2. Building FTS indexes...", nl=False)
        build_fts_indexes(db)
        click.echo(" ✓")

        click.echo("3. Vacuuming database...", nl=False)
        db.execute("VACUUM;")
        click.echo(" ✓")

        # Get final size
        catalog_path = Path(catalog)
        size_mb = catalog_path.stat().st_size / 1024 / 1024

        click.echo("\n" + "=" * 70)
        click.echo(f"✓ Catalog rebuilt: {catalog_path}")
        click.echo(f"✓ Size: {size_mb:.1f} MB")
        click.echo("=" * 70)

    except Exception as e:
        click.echo(f"Rebuild error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('identifier')
@click.option('-c', '--catalog', type=click.Path(exists=True), help='Catalog database path')
@click.option('-n', '--page-num', type=str, help='Page number (optional if in URL)')
@click.option('--num-type', type=click.Choice(['page', 'leaf', 'book']), help='Number type (default: page, or extracted from URL)')
@click.option('-o', '--output', type=str, help='Output file path (suffix determines format)')
@click.option('--format', type=click.Choice(['jp2', 'jpg', 'png']), help='Output format (if -o has no suffix)')
@click.option('--width', type=int, help='Resample to width (maintains aspect ratio)')
@click.option('--quality', type=int, help='JPEG quality (1-95, only for JPG output)')
@click.option('--autocontrast', is_flag=True, help='Apply autocontrast for enhanced contrast')
@click.option('--cutoff', type=int, default=None, help='Autocontrast cutoff percentage (0-100, enables autocontrast if set)')
@click.option('--preserve-tone', is_flag=True, help='Preserve tone in autocontrast (enables autocontrast)')
@click.pass_context
def get_page(ctx, identifier, catalog, page_num, num_type, output, format, width, quality, autocontrast, cutoff, preserve_tone):
    """Download and optionally convert a page image from Internet Archive.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit
    - https://archive.org/details/b31362138/page/n404/ (sequential page, 0-origin)
    - https://archive.org/details/b31362138/page/404/ (book page number)

    Page number and type can be extracted from URL or specified with -n and --num-type.
    Command-line args override URL extraction.

    CATALOG (-c) is optional - needed for book page number lookups. If not provided,
    page_numbers.json is downloaded on-the-fly for book page conversions.

    NUMBER TYPES:
    - page: Sequential page number (default, 0-origin)
    - leaf: Physical leaf/page number
    - book: Book page number (looks up via catalog or downloads page_numbers.json)

    IMAGE PROCESSING OPTIONS:
    - --autocontrast: Enable autocontrast with default cutoff=2
    - --cutoff N: Enable autocontrast with specific cutoff (0-100, default: 2 when autocontrast enabled)
    - --preserve-tone: Enable autocontrast with default cutoff=2 while preserving tone
    - --width N: Resample to width (maintains aspect ratio)
    - --quality N: JPEG quality (1-95)

    Examples:
        ia-utils get-page anatomicalatlasi00smit -n 5 -o page.png
        ia-utils get-page anatomicalatlasi00smit -n 0005 --num-type leaf -o page.jpg --quality 85
        ia-utils get-page https://archive.org/details/b31362138/page/n404/ -o page.png
        ia-utils -v get-page b31362138 -n 42 -c catalog.sqlite --width 1000 --autocontrast
        ia-utils get-page anatomicalatlasi00smit -n 5 --cutoff 5 --width 800 -o page.jpg
    """
    verbose = ctx.obj.get('verbose', False)

    # Extract IA ID and page info from identifier (URL or ID)
    ia_id, page_from_url, page_type_from_url = extract_ia_id_and_page(identifier)

    # Load catalog if provided
    db = None
    if catalog:
        if verbose:
            click.echo(f"Loading IA ID from catalog: {catalog}")
        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                click.echo("Error: No metadata found in catalog database", err=True)
                sys.exit(1)
            ia_id_from_catalog = metadata[0]['ia_identifier']
            # Verify IA ID matches if we extracted one from URL
            if ia_id and ia_id != ia_id_from_catalog:
                click.echo(f"Error: IA ID mismatch - Identifier: {ia_id}, Catalog: {ia_id_from_catalog}", err=True)
                sys.exit(1)
            ia_id = ia_id_from_catalog
        except Exception as e:
            click.echo(f"Error reading catalog database: {e}", err=True)
            sys.exit(1)

    if not ia_id:
        click.echo("Error: Could not determine IA ID from identifier", err=True)
        sys.exit(1)

    # Handle page number: URL extraction → command-line override
    if page_from_url is not None and not page_num:
        page_num = str(page_from_url)

    # Handle page type: URL extraction → command-line override (with 'page' as default)
    if page_type_from_url and not num_type:
        num_type = page_type_from_url
    elif not num_type:
        num_type = 'page'

    # Validate that we have a page number
    if not page_num:
        click.echo("Error: -n/--page-num is required (or provide URL with /page/...)", err=True)
        sys.exit(1)

    # Normalize page number
    try:
        page_number_int = normalize_page_number(page_num)
    except ValueError:
        click.echo(f"Error: Invalid page number: {page_num}", err=True)
        sys.exit(1)

    # Convert to sequential page number if needed
    try:
        sequential_page = get_page_number_for_jp2(page_number_int, num_type, ia_id=ia_id, db=db)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Determine output format and path
    if output:
        output_path = Path(output)
        # Determine format from suffix if not specified
        if format:
            output_format = format.lower()
        else:
            suffix = output_path.suffix.lower().lstrip('.')
            if suffix in ('jp2', 'jpg', 'jpeg', 'png'):
                output_format = 'jpg' if suffix == 'jpeg' else suffix
            elif suffix:
                click.echo(f"Warning: Unknown suffix {suffix}, using {format or 'jp2'}", err=True)
                output_format = format or 'jp2'
            else:
                output_format = format or 'jp2'
    else:
        # Default filename
        output_format = format or 'jp2'
        default_filename = f"{ia_id}_{sequential_page:04d}.{output_format}"
        output_path = Path.cwd() / default_filename

    if verbose:
        click.echo(f"\nDownloading page from: {ia_id}")
        click.echo("=" * 70)

    try:
        download_and_convert_page(
            ia_id,
            sequential_page,
            output_path,
            width=width,
            quality=quality,
            output_format=output_format,
            autocontrast=autocontrast,
            cutoff=cutoff,
            preserve_tone=preserve_tone,
            verbose=verbose
        )

        if verbose:
            click.echo("\n" + "=" * 70)
            click.echo(f"✓ Page saved: {output_path}")
            click.echo("=" * 70)
        else:
            click.echo(str(output_path))

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('identifier')
@click.option('-r', '--range', 'page_range', required=True, type=str, help='Page range (e.g., 1-7,21,25,45)')
@click.option('-p', '--prefix', required=True, type=str, help='Output filename prefix (can include directory path)')
@click.option('-c', '--catalog', type=click.Path(exists=True), help='Catalog database path')
@click.option('--num-type', type=click.Choice(['page', 'leaf', 'book']), default='page', help='Number type (default: page)')
@click.option('--format', type=click.Choice(['jp2', 'jpg', 'png']), default='jpg', help='Output format (default: jpg)')
@click.option('--width', type=int, help='Resample to width (maintains aspect ratio)')
@click.option('--quality', type=int, help='JPEG quality (1-95, only for JPG output)')
@click.option('--autocontrast', is_flag=True, help='Apply autocontrast for enhanced contrast')
@click.option('--cutoff', type=int, default=None, help='Autocontrast cutoff percentage (0-100)')
@click.option('--preserve-tone', is_flag=True, help='Preserve tone in autocontrast')
@click.option('--skip-existing', is_flag=True, help='Skip pages that already exist')
@click.pass_context
def get_pages(ctx, identifier, page_range, prefix, catalog, num_type, format, width, quality, autocontrast, cutoff, preserve_tone, skip_existing):
    """Download and optionally convert multiple page images from Internet Archive.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    PAGE RANGE format (required):
    - Single page: '-r 42'
    - Range: '-r 1-7' (inclusive)
    - Comma-separated: '-r 1,3,5'
    - Mixed: '-r 1-7,21,25,45-50'

    OUTPUT PREFIX (required):
    - Simple: -p myatlas (outputs myatlas_0001.jpg, myatlas_0002.jpg, etc.)
    - With path: -p ./pages/atlas (outputs ./pages/atlas_0001.jpg, etc.)

    NUMBER TYPES:
    - page: Sequential page number (default, 0-origin)
    - leaf: Physical leaf/page number
    - book: Book page number (looks up via catalog or downloads page_numbers.json)

    IMAGE PROCESSING OPTIONS:
    - --autocontrast: Enable autocontrast with default cutoff=2
    - --cutoff N: Enable autocontrast with specific cutoff (0-100)
    - --preserve-tone: Enable autocontrast while preserving tone
    - --width N: Resample to width (maintains aspect ratio)
    - --quality N: JPEG quality (1-95)
    - --skip-existing: Skip pages that already exist

    Examples:
        ia-utils get-pages anatomicalatlasi00smit -r 1-7 -p pages/atlas
        ia-utils get-pages b31362138 -r 1-100,150-160 -p atlas --format jpg --quality 85
        ia-utils -v get-pages anatomicalatlasi00smit -r 1-7,21,25 -p ./output/page --width 1200
    """
    verbose = ctx.obj.get('verbose', False)

    # Extract IA ID from identifier
    ia_id = extract_ia_id(identifier)

    # Load catalog if provided
    db = None
    if catalog:
        if verbose:
            click.echo(f"Loading catalog: {catalog}")
        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                click.echo("Error: No metadata found in catalog database", err=True)
                sys.exit(1)
            ia_id_from_catalog = metadata[0]['ia_identifier']
            # Verify IA ID matches if we extracted one from URL
            if ia_id and ia_id != ia_id_from_catalog:
                click.echo(f"Error: IA ID mismatch - Identifier: {ia_id}, Catalog: {ia_id_from_catalog}", err=True)
                sys.exit(1)
            ia_id = ia_id_from_catalog
        except Exception as e:
            click.echo(f"Error reading catalog database: {e}", err=True)
            sys.exit(1)

    if not ia_id:
        click.echo("Error: Could not determine IA ID from identifier", err=True)
        sys.exit(1)

    # Parse page range
    try:
        pages = parse_page_range(page_range)
    except ValueError as e:
        click.echo(f"Error: Invalid page range: {e}", err=True)
        sys.exit(1)

    if verbose:
        click.echo(f"\nDownloading pages from: {ia_id}")
        click.echo(f"Page range: {page_range} ({len(pages)} pages)")
        click.echo(f"Output prefix: {prefix}")
        click.echo(f"Number type: {num_type}")
        click.echo(f"Format: {format}")
        click.echo("=" * 70)

    # Create directory if prefix contains path
    prefix_path = Path(prefix)
    if prefix_path.parent != Path('.'):
        prefix_path.parent.mkdir(parents=True, exist_ok=True)
        if verbose:
            click.echo(f"Created directory: {prefix_path.parent}")

    # Download pages
    try:
        successful, failed = batch_download_pages(
            ia_id,
            pages,
            prefix,
            width=width,
            quality=quality,
            output_format=format,
            autocontrast=autocontrast,
            cutoff=cutoff,
            preserve_tone=preserve_tone,
            num_type=num_type,
            db=db,
            verbose=verbose,
            skip_existing=skip_existing
        )

        if verbose:
            click.echo("\n" + "=" * 70)
            click.echo(f"✓ Download complete")
            click.echo(f"  Successful: {successful}/{len(pages)}")
            if failed > 0:
                click.echo(f"  Failed: {failed}/{len(pages)}")
            click.echo("=" * 70)
        else:
            click.echo(f"{successful}/{len(pages)} pages downloaded")
            if failed > 0:
                click.echo(f"{failed} pages failed", err=True)

        sys.exit(0 if failed == 0 else 1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
