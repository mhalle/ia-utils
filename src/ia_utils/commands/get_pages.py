"""Get pages command for batch page downloads."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import image
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils


def parse_page_range(range_str: str) -> list:
    """Parse page range string into list of page numbers.

    Supports:
    - Single: '5' -> [5]
    - Range: '1-5' -> [1, 2, 3, 4, 5]
    - Multiple: '1,3,5' -> [1, 3, 5]
    - Mixed: '1-3,5,7-9' -> [1, 2, 3, 5, 7, 8, 9]

    Args:
        range_str: Page range string

    Returns:
        List of page numbers

    Raises:
        ValueError: If range format is invalid
    """
    pages = set()

    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue

        if '-' in part:
            try:
                start_str, end_str = part.split('-', 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
                if start > end:
                    raise ValueError(f"Invalid range: {start} > {end}")
                pages.update(range(start, end + 1))
            except ValueError as e:
                if 'invalid literal' in str(e):
                    raise ValueError(f"Invalid range '{part}': must be integers")
                raise
        else:
            try:
                pages.add(int(part))
            except ValueError:
                raise ValueError(f"Invalid page number: {part}")

    if not pages:
        raise ValueError("No pages specified")

    return sorted(list(pages))


@click.command()
@click.argument('identifier', required=False)
@click.option('-l', '--leaf', type=str, help='Leaf range (e.g., 1-7,21,25)')
@click.option('-b', '--book', type=str, help='Book page range (e.g., 100-150)')
@click.option('-p', '--prefix', required=True, type=str,
              help='Output filename prefix (can include directory path)')
@click.option('-c', '--catalog', type=click.Path(exists=True),
              help='Catalog database path for fast page lookups')
@click.option('--size', type=click.Choice(['small', 'medium', 'large', 'original']),
              default='medium', help='Image size (default: medium)')
@click.option('--format', type=click.Choice(['jp2', 'jpg', 'png']),
              help='Output format (inferred from extension or use default)')
@click.option('--quality', type=int,
              help='JPEG quality (1-95, only for JPG output)')
@click.option('--autocontrast', is_flag=True,
              help='Apply autocontrast for enhanced contrast')
@click.option('--cutoff', type=int, default=None,
              help='Autocontrast cutoff percentage (0-100, enables autocontrast if set)')
@click.option('--preserve-tone', is_flag=True,
              help='Preserve tone in autocontrast (enables autocontrast)')
@click.option('--skip-existing', is_flag=True,
              help='Skip pages that already exist')
@click.pass_context
def get_pages(ctx, identifier, leaf, book, prefix, catalog, size, format,
              quality, autocontrast, cutoff, preserve_tone, skip_existing):
    """Download and optionally convert multiple page images from Internet Archive.

    IDENTIFIER (optional if -c provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - Omit if using -c (catalog contains IA ID)

    PAGE RANGE (one required):
    - Use -l/--leaf for physical scan numbers (direct, fast)
    - Use -b/--book for printed page numbers (requires lookup)

    RANGE FORMAT:
    - Single: '42'
    - Range: '1-7' (inclusive)
    - Comma-separated: '1,3,5'
    - Mixed: '1-7,21,25,45-50'

    OUTPUT PREFIX (required):
    - Simple: -p myatlas (outputs myatlas_0001.jpg, myatlas_0002.jpg, etc.)
    - With path: -p ./pages/atlas (outputs ./pages/atlas_0001.jpg, etc.)

    IMAGE SIZES:
    - small: ~100px (API, very fast)
    - medium: ~256px (API, default, fast)
    - large: ~512px (API, fast)
    - original: JP2 lossless (slower, highest quality)

    IMAGE PROCESSING OPTIONS:
    - --autocontrast: Enable autocontrast with default cutoff=2
    - --cutoff N: Enable autocontrast with specific cutoff (0-100)
    - --preserve-tone: Enable autocontrast while preserving tone
    - --quality N: JPEG quality (1-95)
    - --skip-existing: Skip pages that already exist

    Examples:
        ia-utils get-pages anatomicalatlasi00smit -l 1-7 -p pages/atlas
        ia-utils get-pages -c catalog.sqlite -l 1-7 -p pages/atlas
        ia-utils get-pages -c catalog.sqlite -b 100-150 -p atlas
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID from identifier (if provided)
    ia_id = None
    if identifier:
        ia_id = page_utils.extract_ia_id(identifier)

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
            # Verify IA ID matches if identifier was also provided
            if ia_id and ia_id != ia_id_from_catalog:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Catalog: {ia_id_from_catalog}")
                sys.exit(1)
            ia_id = ia_id_from_catalog
        except Exception as e:
            logger.error(f"Failed to read catalog database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("IDENTIFIER required (or use -c with catalog)")
        sys.exit(1)

    # Validate mutually exclusive options
    if leaf and book:
        logger.error("Cannot specify both --leaf and --book")
        sys.exit(1)

    if not leaf and not book:
        logger.error("Page range required: use -l/--leaf or -b/--book")
        sys.exit(1)

    # Determine page range and type
    if leaf:
        page_range = leaf
        num_type = 'leaf'
    else:
        page_range = book
        num_type = 'book'

    # Parse page range
    try:
        pages = parse_page_range(page_range)
    except ValueError as e:
        logger.error(f"Invalid page range: {e}")
        sys.exit(1)

    # Determine output format
    output_format = format
    if not output_format:
        # Try to infer from prefix
        prefix_lower = prefix.lower()
        if prefix_lower.endswith('.jpg') or prefix_lower.endswith('.jpeg'):
            output_format = 'jpg'
        elif prefix_lower.endswith('.png'):
            output_format = 'png'
        elif prefix_lower.endswith('.jp2'):
            output_format = 'jp2'
        else:
            output_format = 'jpg'

    if verbose:
        logger.section(f"Downloading pages from: {ia_id}")
        logger.info(f"   Page range: {page_range} ({len(pages)} pages)")
        logger.info(f"   Output prefix: {prefix}")
        logger.info(f"   Number type: {num_type}")
        logger.info(f"   Size: {size}")
        logger.info(f"   Format: {output_format}")

    # Create directory if prefix contains path
    prefix_path = Path(prefix)
    if prefix_path.parent != Path('.'):
        prefix_path.parent.mkdir(parents=True, exist_ok=True)
        if verbose:
            logger.info(f"   Created directory: {prefix_path.parent}")

    # Download pages
    try:
        successful = 0
        failed = 0
        skipped = 0

        if verbose:
            logger.subsection(f"\nDownloading {len(pages)} pages...")

        for idx, page_num in enumerate(pages, 1):
            try:
                # Convert to leaf number (canonical format for all image fetching)
                try:
                    leaf_num = page_utils.get_leaf_num(page_num, num_type, ia_id=ia_id, db=db)
                except ValueError as e:
                    logger.error(f"Page {page_num}: {e}")
                    failed += 1
                    continue

                # Generate output filename (uses input page_num for consistency)
                output_filename = f"{prefix}_{page_num:04d}.{output_format}"
                output_path = Path(output_filename)

                # Check if file exists and skip if requested
                if skip_existing and output_path.exists():
                    if verbose:
                        logger.progress(f"  [{idx}/{len(pages)}] Skipping {output_path.name} (exists)")
                    skipped += 1
                    continue

                if verbose:
                    leaf_info = f"leaf {leaf_num}" if num_type == 'book' else f"{page_num}"
                    logger.progress(f"  [{idx}/{len(pages)}] {leaf_info}...", nl=False)

                # Download and convert using leaf number
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
                    logger=logger if verbose else None
                )

                if verbose:
                    logger.progress_done("✓")

                successful += 1

            except Exception as e:
                if verbose:
                    logger.progress_fail(f"✗ {e}")
                else:
                    logger.error(f"Page {page_num}: {e}")
                failed += 1

        if verbose:
            logger.section("Complete")
            logger.info(f"✓ Downloaded: {successful}/{len(pages)}")
            if skipped > 0:
                logger.info(f"✓ Skipped: {skipped}")
            if failed > 0:
                logger.info(f"✗ Failed: {failed}")
        else:
            if failed == 0:
                click.echo(f"{successful}/{len(pages)} pages downloaded")
            else:
                click.echo(f"{successful}/{len(pages)} pages downloaded, {failed} failed", err=True)

        sys.exit(0 if failed == 0 else 1)

    except Exception as e:
        logger.error(f"Download failed: {e}")
        sys.exit(1)
