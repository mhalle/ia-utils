"""Get pages command for batch page downloads."""

import sys
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED
import click
import sqlite_utils
from joblib import Parallel, delayed

from ia_utils.core import image, ia_client
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
@click.option('--all', 'download_all', is_flag=True,
              help='Download all pages')
@click.option('-p', '--prefix', type=str,
              help='Output filename prefix (required for individual files)')
@click.option('-o', '--output', type=str,
              help='Output ZIP filename (for --zip mode)')
@click.option('-c', '--catalog', type=click.Path(exists=True),
              help='Catalog database path for page lookups and auto-naming')
@click.option('--zip', 'as_zip', is_flag=True,
              help='Output as ZIP file instead of individual files')
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
@click.option('-j', '--jobs', type=int, default=4,
              help='Parallel jobs for --zip mode (default: 4)')
@click.pass_context
def get_pages(ctx, identifier, leaf, book, download_all, prefix, output, catalog,
              as_zip, size, format, quality, autocontrast, cutoff, preserve_tone,
              skip_existing, jobs):
    """Download page images from Internet Archive.

    IDENTIFIER (optional if -c provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - Omit if using -c (catalog contains IA ID)

    PAGE SELECTION (one required):

    \b
    -l/--leaf     Leaf range (e.g., 1-7,21,25)
    -b/--book     Book page range (e.g., 100-150)
    --all         All pages (requires -c or fetches metadata)

    OUTPUT MODES:

    \b
    Individual files (default):
      -p prefix     Output as prefix_0001.jpg, prefix_0002.jpg, etc.
    ZIP archive:
      --zip         Output as ZIP file
      -o file.zip   ZIP filename (auto-named for --all --zip)

    IMAGE SIZES:

    \b
    small     ~100px (very fast)
    medium    ~256px (default)
    large     ~512px
    original  JP2 lossless (individual files only)

    IMAGE PROCESSING (individual files only):

    \b
    --autocontrast    Enable autocontrast
    --cutoff N        Autocontrast cutoff (0-100)
    --preserve-tone   Preserve tone in autocontrast
    --quality N       JPEG quality (1-95)
    --skip-existing   Skip existing files

    EXAMPLES:

    \b
    # Download range as individual files
    ia-utils get-pages -c book.sqlite -l 1-7 -p pages/atlas
    # Download all pages as ZIP (auto-named)
    ia-utils get-pages -c book.sqlite --all --zip
    # Download range as ZIP
    ia-utils get-pages -c book.sqlite -l 100-200 --zip -o chapter5.zip
    # Download with image processing
    ia-utils get-pages -c book.sqlite -l 1-10 -p out --autocontrast
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID from identifier (if provided)
    ia_id = None
    slug = None
    if identifier:
        ia_id = page_utils.extract_ia_id(identifier)

    # Load catalog if provided
    db = None
    total_pages = None
    if catalog:
        if verbose:
            logger.info(f"Loading catalog: {catalog}")
        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                logger.error("No metadata found in catalog database")
                sys.exit(1)
            ia_id_from_catalog = metadata[0]['identifier']
            slug = metadata[0].get('slug', '')
            # Verify IA ID matches if identifier was also provided
            if ia_id and ia_id != ia_id_from_catalog:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Catalog: {ia_id_from_catalog}")
                sys.exit(1)
            ia_id = ia_id_from_catalog

            # Get page count from catalog for --all mode
            if download_all:
                try:
                    pages_rows = list(db.execute("SELECT DISTINCT page_id FROM text_blocks ORDER BY page_id").fetchall())
                    total_pages = len(pages_rows)
                    if verbose:
                        logger.info(f"Found {total_pages} pages in catalog")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to read catalog database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("IDENTIFIER required (or use -c with catalog)")
        sys.exit(1)

    # Validate page selection options
    page_options = sum([bool(leaf), bool(book), bool(download_all)])
    if page_options == 0:
        logger.error("Page selection required: use -l/--leaf, -b/--book, or --all")
        sys.exit(1)
    if page_options > 1:
        logger.error("Cannot combine --leaf, --book, and --all")
        sys.exit(1)

    # Validate output options
    if as_zip:
        # ZIP mode validations
        if size == 'original':
            logger.error("--zip mode does not support --size original")
            sys.exit(1)
        if any([autocontrast, cutoff, preserve_tone, quality]):
            logger.error("--zip mode does not support image processing options")
            sys.exit(1)
        if prefix:
            logger.error("Use -o/--output for ZIP filename, not -p/--prefix")
            sys.exit(1)
        if not download_all and not output:
            logger.error("--zip requires -o/--output for page ranges (auto-named only for --all)")
            sys.exit(1)
    else:
        # Individual files mode
        if not prefix:
            logger.error("-p/--prefix required for individual files")
            sys.exit(1)
        if output:
            logger.error("-o/--output is for --zip mode; use -p/--prefix for individual files")
            sys.exit(1)

    # Get total pages for --all mode
    if download_all:
        if total_pages is None:
            # Fetch from IA metadata
            if verbose:
                logger.progress("Fetching page count from metadata...", nl=False)
            try:
                meta = ia_client.get_metadata(ia_id)
                total_pages = int(meta.get('imagecount', 0))
                if verbose:
                    logger.progress_done(f"✓ ({total_pages} pages)")
            except Exception as e:
                logger.error(f"Failed to get page count: {e}")
                sys.exit(1)

        if total_pages == 0:
            logger.error(f"No pages found for {ia_id}")
            sys.exit(1)

        pages = list(range(1, total_pages + 1))
        num_type = 'leaf'
    elif leaf:
        try:
            pages = parse_page_range(leaf)
        except ValueError as e:
            logger.error(f"Invalid leaf range: {e}")
            sys.exit(1)
        num_type = 'leaf'
    else:  # book
        try:
            pages = parse_page_range(book)
        except ValueError as e:
            logger.error(f"Invalid book page range: {e}")
            sys.exit(1)
        num_type = 'book'

    # Handle ZIP output mode
    if as_zip:
        _download_as_zip(
            ia_id=ia_id,
            slug=slug,
            pages=pages,
            num_type=num_type,
            output=output,
            download_all=download_all,
            size=size,
            jobs=jobs,
            db=db,
            logger=logger,
            verbose=verbose
        )
        return

    # Individual files mode
    _download_individual_files(
        ia_id=ia_id,
        pages=pages,
        num_type=num_type,
        prefix=prefix,
        size=size,
        format=format,
        quality=quality,
        autocontrast=autocontrast,
        cutoff=cutoff,
        preserve_tone=preserve_tone,
        skip_existing=skip_existing,
        db=db,
        logger=logger,
        verbose=verbose
    )


def _download_single_page(args):
    """Download a single page image (top-level for pickling)."""
    page_num, ia_id, size = args
    # For --all mode, page_num is already a leaf number
    leaf_num = page_num

    # API pages are 0-indexed
    api_page = leaf_num - 1

    # Download image bytes directly from IA
    source = image.APIImageSource(size=size)
    image_bytes = source.fetch(ia_id, api_page)

    # Use standard IA naming: {ia_id}_0001.jpg, etc.
    filename = f"{ia_id}_{leaf_num:04d}.jpg"
    return (filename, image_bytes)


def _download_as_zip(ia_id, slug, pages, num_type, output, download_all, size,
                     jobs, db, logger, verbose):
    """Download pages as a ZIP archive with parallel downloads."""
    # Determine output filename
    if output:
        output_path = Path(output)
    else:
        # Auto-name for --all mode
        name = slug if slug else ia_id
        output_path = Path(f"{name}.zip")

    if verbose:
        logger.section(f"Downloading {len(pages)} pages from: {ia_id}")
        logger.info(f"   Size: {size}")
        logger.info(f"   Output: {output_path}")
        logger.info(f"   Parallel jobs: {jobs}")

    # Try to download page_numbers.json for inclusion in ZIP
    page_numbers_data = None
    if verbose:
        logger.progress("Downloading page_numbers.json...", nl=False)
    try:
        page_numbers_data = ia_client.download_json(ia_id, f"{ia_id}_page_numbers.json", logger=logger, verbose=False)
        if page_numbers_data and 'pages' in page_numbers_data:
            if verbose:
                logger.progress_done(f"✓ ({len(page_numbers_data['pages'])} pages)")
        else:
            page_numbers_data = None
            if verbose:
                logger.progress_done("(not available)")
    except Exception:
        page_numbers_data = None
        if verbose:
            logger.progress_done("(not available)")

    # Convert book pages to leaf numbers if needed
    if num_type == 'book':
        leaf_pages = []
        for page_num in pages:
            try:
                leaf_num = page_utils.get_leaf_num(page_num, num_type, ia_id=ia_id, db=db)
                leaf_pages.append(leaf_num)
            except ValueError as e:
                logger.error(f"Page {page_num}: {e}")
        pages = leaf_pages

    # Prepare args for parallel download
    download_args = [(page_num, ia_id, size) for page_num in pages]

    # Download all pages in parallel
    try:
        if verbose:
            logger.subsection(f"\nDownloading {len(pages)} pages in parallel ({jobs} jobs)...")

        # Use joblib for parallel downloads
        results = Parallel(n_jobs=jobs, verbose=10 if verbose else 0)(
            delayed(_download_single_page)(args) for args in download_args
        )

        if verbose:
            logger.subsection(f"\nWriting ZIP file...")

        # Write ZIP file with uncompressed storage
        with ZipFile(output_path, 'w', compression=ZIP_STORED) as zf:
            for filename, data in results:
                zf.writestr(filename, data)
                if verbose:
                    logger.progress(f"   Added: {filename}")

            # Add page_numbers.json if available
            if page_numbers_data:
                json_data = json.dumps(page_numbers_data, indent=2)
                zf.writestr(f"{ia_id}_page_numbers.json", json_data)
                if verbose:
                    logger.progress(f"   Added: {ia_id}_page_numbers.json")

        if verbose:
            zip_size_mb = output_path.stat().st_size / 1024 / 1024
            logger.section("Complete")
            logger.info(f"✓ ZIP created: {output_path}")
            logger.info(f"✓ Size: {zip_size_mb:.1f} MB")
            logger.info(f"✓ Pages: {len(pages)}")
        else:
            click.echo(str(output_path))

    except Exception as e:
        import traceback
        logger.error(f"Failed to create ZIP archive: {e}")
        if verbose:
            traceback.print_exc()
        sys.exit(1)


def _download_individual_files(ia_id, pages, num_type, prefix, size, format,
                                quality, autocontrast, cutoff, preserve_tone,
                                skip_existing, db, logger, verbose):
    """Download pages as individual files."""
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
        logger.info(f"   Pages: {len(pages)}")
        logger.info(f"   Output prefix: {prefix}")
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
