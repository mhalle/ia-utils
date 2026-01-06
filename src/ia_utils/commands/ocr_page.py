"""OCR page command - run pytesseract on Internet Archive pages."""

import sys
import json
from pathlib import Path
from typing import Optional, Tuple
from io import BytesIO

import click
import sqlite_utils

from ia_utils.core import ia_client
from ia_utils.core.database import get_document_metadata
from ia_utils.core.image import JP2ImageSource
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils

import pytesseract
from PIL import Image


def parse_bbox(bbox_str: str) -> Tuple[int, int, int, int]:
    """Parse bbox string in multiple formats.

    Supported formats:
        - Comma-separated: "73,1101,2063,1352"
        - Space-separated: "73 1101 2063 1352"
        - hOCR format: "bbox 73 1101 2063 1352"

    Returns:
        Tuple of (left, top, right, bottom)
    """
    s = bbox_str.strip()

    # Strip "bbox " prefix if present
    if s.lower().startswith('bbox '):
        s = s[5:].strip()

    # Try comma-separated first
    if ',' in s:
        parts = [int(x.strip()) for x in s.split(',')]
    else:
        # Space-separated
        parts = [int(x) for x in s.split()]

    if len(parts) != 4:
        raise ValueError(f"bbox must have 4 values, got {len(parts)}")

    return tuple(parts)


def get_language_from_index(db: sqlite_utils.Database) -> Optional[str]:
    """Get language from index metadata."""
    try:
        meta = get_document_metadata(db)
        if meta and meta.get('language'):
            lang = meta['language']
            # Map common IA language codes to tesseract codes
            lang_map = {
                'eng': 'eng',
                'English': 'eng',
                'ger': 'deu',
                'German': 'deu',
                'fre': 'fra',
                'French': 'fra',
                'spa': 'spa',
                'Spanish': 'spa',
                'ita': 'ita',
                'Italian': 'ita',
                'lat': 'lat',
                'Latin': 'lat',
            }
            return lang_map.get(lang, lang)
    except Exception:
        pass
    return None


def ocr_image(
    img: Image.Image,
    lang: str = 'eng',
    psm: int = 3,
    oem: int = 3,
) -> str:
    """Run pytesseract OCR on an image.

    Args:
        img: PIL Image
        lang: Tesseract language code
        psm: Page segmentation mode (default 3 = auto)
        oem: OCR engine mode (default 3 = default/best)

    Returns:
        Extracted text
    """
    config = f"--oem {oem} --psm {psm}"
    return pytesseract.image_to_string(img, lang=lang, config=config)


@click.command('ocr-page')
@click.argument('identifier', required=False)
@click.option('-l', '--leaf', type=int, help='Leaf number (physical scan order)')
@click.option('-b', '--book', type=int, help='Book page number (printed page, requires lookup)')
@click.option('-i', '--index', type=click.Path(exists=True), help='Index database path')
@click.option('--bbox', type=str, help='Bounding box: "l,t,r,b" or "l t r b" or "bbox l t r b"')
@click.option('--lang', type=str, help='Tesseract language code (default: from index or eng)')
@click.option('--psm', type=int, default=3, help='Page segmentation mode (default: 3 = auto)')
@click.option('--oem', type=int, default=3, help='OCR engine mode (default: 3 = best available)')
@click.option('-o', '--output', type=str, help='Output file path (.txt or .json)')
@click.option('--output-format', type=click.Choice(['text', 'json']), help='Output format (auto from -o suffix)')
@click.pass_context
def ocr_page(ctx, identifier, leaf, book, index, bbox, lang, psm, oem, output, output_format):
    """Run OCR on an Internet Archive page using pytesseract.

    Requires tesseract binary (tesseract-ocr on some Linux systems).

    Fetches the original JP2 image and runs local OCR, which often
    produces better results than IA's stored OCR.

    IDENTIFIER (optional if -i provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - URL with page: https://archive.org/details/b31362138/page/leaf5/

    PAGE NUMBER:
    - Use -l/--leaf for physical scan number (direct)
    - Use -b/--book for printed page number (requires index or fetches mapping)
    - Can also extract from URL (/page/leafN/ or /page/N/)

    BOUNDING BOX:
    - Crop to region before OCR (useful for re-OCRing specific blocks)
    - Format: left,top,right,bottom (pixels)
    - Also accepts hOCR format: "bbox 73 1101 2063 1352"

    OUTPUT:
    - Default: text to stdout
    - With -o file.txt: plain text to file
    - With -o file.json: JSON with metadata

    Examples:
        ia-utils ocr-page anatomicalatlasi00smit -l 15
        ia-utils ocr-page -i index.sqlite -l 15 --bbox 73,1101,2063,1352
        ia-utils ocr-page -i index.sqlite -b 42 -o page.json
        ia-utils ocr-page https://archive.org/details/b31362138/page/leaf100/
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID and page info from identifier (if provided)
    ia_id = None
    page_from_url = None
    page_type_from_url = None
    if identifier:
        ia_id, page_from_url, page_type_from_url = page_utils.extract_ia_id_and_page(identifier)

    # Load index if provided
    db = None
    if index:
        if verbose:
            logger.info(f"Loading index: {index}")
        try:
            db = sqlite_utils.Database(index)
            doc_metadata = get_document_metadata(db)
            if not doc_metadata:
                logger.error("No metadata found in index database")
                sys.exit(1)
            ia_id_from_index = doc_metadata['identifier']
            if ia_id and ia_id != ia_id_from_index:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Index: {ia_id_from_index}")
                sys.exit(1)
            ia_id = ia_id_from_index
        except Exception as e:
            logger.error(f"Failed to read index database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("IDENTIFIER required (or use -i with index)")
        sys.exit(1)

    # Validate mutually exclusive options
    if leaf is not None and book is not None:
        logger.error("Cannot specify both --leaf and --book")
        sys.exit(1)

    # Determine page number and type
    if leaf is not None:
        page_number_int = leaf
        num_type = 'leaf'
    elif book is not None:
        page_number_int = book
        num_type = 'book'
    elif page_from_url is not None:
        page_number_int = page_from_url
        num_type = page_type_from_url or 'leaf'
    else:
        logger.error("Page number required: use -l/--leaf or -b/--book")
        sys.exit(1)

    # Convert to leaf number
    try:
        leaf_num = page_utils.get_leaf_num(page_number_int, num_type, ia_id=ia_id, db=db)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Determine language
    if lang is None:
        if db:
            lang = get_language_from_index(db) or 'eng'
        else:
            lang = 'eng'

    # Determine output format
    if output_format is None and output:
        suffix = Path(output).suffix.lower()
        if suffix == '.json':
            output_format = 'json'
        else:
            output_format = 'text'
    elif output_format is None:
        output_format = 'text'

    if verbose:
        logger.section(f"OCR page from: {ia_id}")
        logger.info(f"   Leaf: {leaf_num}" + (f" (from {num_type} {page_number_int})" if num_type == 'book' else ""))
        logger.info(f"   Language: {lang}")
        logger.info(f"   PSM: {psm}, OEM: {oem}")
        if bbox:
            logger.info(f"   Bbox: {bbox}")

    # Fetch JP2 image
    if verbose:
        logger.progress("   Fetching JP2...", nl=False)

    try:
        source = JP2ImageSource()
        image_bytes = source.fetch(ia_id, leaf_num)
        if verbose:
            size_kb = len(image_bytes) / 1024
            logger.progress_done(f"({size_kb:.0f} KB)")
    except Exception as e:
        if verbose:
            logger.progress_fail("failed")
        logger.error(f"Failed to fetch image: {e}")
        sys.exit(1)

    # Open and optionally crop image
    img = Image.open(BytesIO(image_bytes))

    crop_box = None
    if bbox:
        try:
            crop_box = parse_bbox(bbox)
            img = img.crop(crop_box)
            if verbose:
                logger.info(f"   Cropped to: {crop_box}")
        except ValueError as e:
            logger.error(f"Invalid bbox: {e}")
            sys.exit(1)

    # Run OCR
    if verbose:
        logger.progress("   Running OCR...", nl=False)

    try:
        text = ocr_image(img, lang=lang, psm=psm, oem=oem)
        if verbose:
            logger.progress_done(f"({len(text)} chars)")
    except Exception as e:
        if verbose:
            logger.progress_fail("failed")
        logger.error(f"OCR failed: {e}")
        sys.exit(1)

    # Prepare output
    if output_format == 'json':
        result = {
            'identifier': ia_id,
            'leaf': leaf_num,
            'lang': lang,
            'psm': psm,
            'oem': oem,
            'bbox': list(crop_box) if crop_box else None,
            'text': text,
        }
        output_str = json.dumps(result, indent=2)
    else:
        output_str = text

    # Write output
    if output:
        Path(output).write_text(output_str)
        if verbose:
            logger.section("Complete")
            logger.info(f"Saved: {output}")
        else:
            click.echo(output)
    else:
        click.echo(output_str)
