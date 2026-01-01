"""Get page command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import image
from ia_utils.core.database import get_document_metadata, get_index_metadata
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils


@click.command()
@click.argument('identifier', required=False)
@click.option('-l', '--leaf', type=int, help='Leaf number (physical scan order)')
@click.option('-b', '--book', type=int, help='Book page number (printed page, requires lookup)')
@click.option('-i', '--index', type=click.Path(exists=True), help='Index database path')
@click.option('-o', '--output', type=str, help='Output file path (suffix determines format)')
@click.option('--size', type=click.Choice(['small', 'medium', 'large', 'original']),
              default='medium', help='Image size (default: medium)')
@click.option('--format', type=click.Choice(['jp2', 'jpg', 'png']), help='Output format (if -o has no suffix)')
@click.option('--quality', type=int, help='JPEG quality (1-95, only for JPG output)')
@click.option('--autocontrast', is_flag=True, help='Apply autocontrast for enhanced contrast')
@click.option('--cutoff', type=int, default=None, help='Autocontrast cutoff percentage (0-100, enables autocontrast if set)')
@click.option('--preserve-tone', is_flag=True, help='Preserve tone in autocontrast (enables autocontrast)')
@click.pass_context
def get_page(ctx, identifier, leaf, book, index, output, size, format, quality, autocontrast, cutoff, preserve_tone):
    """Download and optionally convert a page image from Internet Archive.

    IDENTIFIER (optional if -i provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - URL with page: https://archive.org/details/b31362138/page/leaf5/
    - Omit if using -i (index contains IA ID)

    PAGE NUMBER:
    - Use -l/--leaf for physical scan number (direct, fast)
    - Use -b/--book for printed page number (requires lookup)
    - Can also extract from URL (/page/leafN/ or /page/N/)

    INDEX (-i):
    - Required if IDENTIFIER is omitted
    - Speeds up book page lookups (uses cached page_numbers table)
    - Validates IA ID matches if identifier is also provided

    OUTPUT:
    - Default: {ia_id}_{leaf:04d}.{format}
    - With -o: Use provided path
    - Format: Inferred from suffix (.jpg, .png, .jp2) or --format flag

    IMAGE SIZES:
    - small: ~300px width (API, very fast)
    - medium: ~600px width (API, default, fast)
    - large: full resolution (API, fast)
    - original: full resolution JP2 lossless (slower, highest quality)

    Examples:
        ia-utils get-page anatomicalatlasi00smit -l 5 -o page.png
        ia-utils get-page -i index.sqlite -l 5 -o page.png
        ia-utils get-page https://archive.org/details/b31362138/page/leaf5/
        ia-utils get-page -i index.sqlite -b 42
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
            # Verify IA ID matches if identifier was also provided
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

    # Determine page number and type from flags or URL
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
        logger.error("Page number required: use -l/--leaf or -b/--book (or provide URL with /page/...)")
        sys.exit(1)

    # Convert to leaf number (canonical format for all image fetching)
    try:
        leaf_num = page_utils.get_leaf_num(page_number_int, num_type, ia_id=ia_id, db=db)
    except ValueError as e:
        logger.error(str(e))
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
                logger.warning(f"Unknown suffix {suffix}, using {format or 'jpg'}")
                output_format = format or 'jpg'
            else:
                output_format = format or 'jpg'
    else:
        # Default filename uses leaf number
        output_format = format or 'jpg'
        default_filename = f"{ia_id}_{leaf_num:04d}.{output_format}"
        output_path = Path.cwd() / default_filename

    if verbose:
        logger.section(f"Downloading page from: {ia_id}")
        logger.info(f"   Leaf: {leaf_num}" + (f" (from {num_type} {page_number_int})" if num_type == 'book' else ""))
        logger.info(f"   Size: {size}")
        logger.info(f"   Format: {output_format}")

    try:
        image.download_and_convert_page(
            ia_id,
            leaf_num,
            output_path,
            size=size,
            output_format=output_format,
            quality=quality,
            autocontrast=autocontrast,
            cutoff=cutoff,
            preserve_tone=preserve_tone,
            logger=logger
        )

        if verbose:
            logger.section("Complete")
            logger.info(f"✓ Page saved: {output_path}")
        else:
            click.echo(str(output_path))

    except Exception as e:
        logger.error(str(e))
        sys.exit(1)
