"""Get page command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import image
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils


@click.command()
@click.argument('identifier')
@click.option('-c', '--catalog', type=click.Path(exists=True), help='Catalog database path')
@click.option('-n', '--page-num', type=str, help='Page number (optional if in URL)')
@click.option('--num-type', type=click.Choice(['page', 'leaf', 'book']), help='Number type (default: page, or extracted from URL)')
@click.option('-o', '--output', type=str, help='Output file path (suffix determines format)')
@click.option('--size', type=click.Choice(['small', 'medium', 'large', 'original']),
              default='medium', help='Image size (default: medium)')
@click.option('--format', type=click.Choice(['jp2', 'jpg', 'png']), help='Output format (if -o has no suffix)')
@click.option('--quality', type=int, help='JPEG quality (1-95, only for JPG output)')
@click.option('--autocontrast', is_flag=True, help='Apply autocontrast for enhanced contrast')
@click.option('--cutoff', type=int, default=None, help='Autocontrast cutoff percentage (0-100, enables autocontrast if set)')
@click.option('--preserve-tone', is_flag=True, help='Preserve tone in autocontrast (enables autocontrast)')
@click.pass_context
def get_page(ctx, identifier, catalog, page_num, num_type, output, size, format, quality, autocontrast, cutoff, preserve_tone):
    """Download and optionally convert a page image from Internet Archive.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit
    - https://archive.org/details/b31362138/page/n404/ (sequential page)
    - https://archive.org/details/b31362138/page/404/ (book page number)

    PAGE NUMBER & TYPE:
    - Extract from URL if available (/page/nXXX/ or /page/XXX/)
    - Override with -n/--page-num and --num-type if provided
    - Default to 'page' type if not specified
    - Priority: Command-line flags > URL extraction > defaults

    CATALOG (-c, optional):
    - Speeds up book page lookups (uses cached page_numbers table)
    - Validates IA ID matches if identifier is a URL
    - If not provided, page_numbers.json downloaded on-demand for book pages

    OUTPUT:
    - Default: {ia_id}_{page:04d}.{format}
    - With -o: Use provided path
    - Format: Inferred from suffix (.jpg, .png, .jp2) or --format flag

    IMAGE SIZES:
    - small: ~100px (API, very fast)
    - medium: ~256px (API, default, fast)
    - large: ~512px (API, fast)
    - original: JP2 lossless (slower, highest quality)

    Examples:
        ia-utils get-page anatomicalatlasi00smit -n 5 -o page.png
        ia-utils get-page anatomicalatlasi00smit -n 5 --size large
        ia-utils get-page https://archive.org/details/b31362138/page/n404/ -o page.png
        ia-utils -v get-page b31362138 -n 42 -c catalog.sqlite --size original
        ia-utils get-page anatomicalatlasi00smit -n 5 --size original --autocontrast --quality 90
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID and page info from identifier (URL or ID)
    ia_id, page_from_url, page_type_from_url = page_utils.extract_ia_id_and_page(identifier)

    # Load catalog if provided
    db = None
    if catalog:
        if verbose:
            logger.info(f"Loading catalog: {catalog}")
        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                logger.error("No metadata found in catalog database")
                sys.exit(1)
            ia_id_from_catalog = metadata[0]['ia_identifier']
            # Verify IA ID matches if we extracted one from URL
            if ia_id and ia_id != ia_id_from_catalog:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Catalog: {ia_id_from_catalog}")
                sys.exit(1)
            ia_id = ia_id_from_catalog
        except Exception as e:
            logger.error(f"Failed to read catalog database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("Could not determine IA ID from identifier")
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
        logger.error("-n/--page-num is required (or provide URL with /page/...)")
        sys.exit(1)

    # Normalize page number
    try:
        page_number_int = page_utils.normalize_page_number(page_num)
    except ValueError:
        logger.error(f"Invalid page number: {page_num}")
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
        # Default filename
        output_format = format or 'jpg'
        default_filename = f"{ia_id}_{page_number_int:04d}.{output_format}"
        output_path = Path.cwd() / default_filename

    if verbose:
        logger.section(f"Downloading page from: {ia_id}")
        logger.info(f"   Page: {page_number_int} (type: {num_type})")
        logger.info(f"   Size: {size}")
        logger.info(f"   Format: {output_format}")

    # For API images, page numbering is 0-origin sequential
    # For JP2 (original), page numbering is 1-origin sequential (needs conversion if using leaf/book)
    if size == 'original':
        # Convert to sequential page number if needed
        try:
            sequential_page = page_utils.get_page_number_for_jp2(page_number_int, num_type, ia_id=ia_id, db=db)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
        # JP2 pages are 1-indexed, but API expects 0-indexed, so keep as is for JP2
        api_page = sequential_page - 1 if num_type != 'page' else sequential_page
    else:
        # API pages are 0-indexed, so use page_number_int directly for sequential pages
        # For book/leaf, we need to convert first
        if num_type in ('leaf', 'book'):
            try:
                sequential_page = page_utils.get_page_number_for_jp2(page_number_int, num_type, ia_id=ia_id, db=db)
                api_page = sequential_page - 1  # Convert 1-indexed to 0-indexed for API
            except ValueError as e:
                logger.error(str(e))
                sys.exit(1)
        else:
            # Already sequential
            api_page = page_number_int

    try:
        image.download_and_convert_page(
            ia_id,
            api_page,
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
