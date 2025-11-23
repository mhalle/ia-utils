"""Get all book pages command with parallel downloads."""

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


@click.command()
@click.argument('identifier')
@click.option('-o', '--output', type=str, help='Output ZIP filename (default: {ia_id}.zip)')
@click.option('-c', '--catalog', type=click.Path(exists=True),
              help='Catalog database path (provides page count and page_numbers.json)')
@click.option('--size', type=click.Choice(['small', 'medium', 'large']),
              default='small', help='Image size (default: small, fastest)')
@click.option('-j', '--jobs', type=int, default=4,
              help='Number of parallel jobs (default: 4)')
@click.pass_context
def get_book_pages(ctx, identifier, output, catalog, size, jobs):
    """Download all pages of an Internet Archive book as a ZIP file.

    Creates a ZIP archive with uncompressed storage containing:
    - All page images named as {ia_id}_0001.jpg, {ia_id}_0002.jpg, etc.
    - Optional: page_numbers.json (if available) with page mappings

    The ZIP uses no compression (STORED) for faster creation and direct streaming.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    IMAGE SIZES:
    - small: ~100px (default, very fast)
    - medium: ~256px (faster than large)
    - large: ~512px (slower)

    PARALLEL DOWNLOADS:
    - Use -j/--jobs to control parallel downloads (default: 4)
    - Higher values = faster but more bandwidth; be respectful to IA servers

    Examples:
        ia-utils get-book-pages anatomicalatlasi00smit
        ia-utils get-book-pages anatomicalatlasi00smit -o mybook.zip --size medium
        ia-utils get-book-pages -c catalog.sqlite -j 8
        ia-utils -v get-book-pages anatomicalatlasi00smit --size large
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID from identifier
    ia_id = page_utils.extract_ia_id(identifier)

    # Load catalog if provided
    db = None
    total_pages = None
    page_numbers_data = None

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

            # Get page count from text_blocks
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
        logger.error("Could not determine IA ID from identifier")
        sys.exit(1)

    # If no catalog, get page count from metadata
    if total_pages is None:
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

    # Try to download page_numbers.json
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

    # Determine output filename
    if not output:
        output = f"{ia_id}.zip"
    output_path = Path(output)

    if verbose:
        logger.section(f"Downloading {total_pages} pages from: {ia_id}")
        logger.info(f"   Size: {size}")
        logger.info(f"   Output: {output_path}")
        logger.info(f"   Parallel jobs: {jobs}")

    # Function to download a single page
    def download_page(page_num):
        """Download a single page image."""
        try:
            # API pages are 0-indexed
            api_page = page_num - 1

            # Download image bytes directly from IA
            source = image.APIImageSource(size=size)
            image_bytes = source.fetch(ia_id, api_page)

            # Use standard IA naming: {ia_id}_0001.jpg, etc.
            filename = f"{ia_id}_{page_num:04d}.jpg"
            return (filename, image_bytes)

        except Exception as e:
            if verbose:
                logger.error(f"Page {page_num}: {e}")
            raise

    # Download all pages in parallel
    try:
        if verbose:
            logger.subsection(f"\nDownloading {total_pages} pages in parallel ({jobs} jobs)...")

        pages = list(range(1, total_pages + 1))

        # Use joblib for parallel downloads
        results = Parallel(n_jobs=jobs, verbose=10 if verbose else 0)(
            delayed(download_page)(page_num) for page_num in pages
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
            logger.info(f"✓ Pages: {total_pages}")
        else:
            click.echo(str(output_path))

    except Exception as e:
        import traceback
        logger.error(f"Failed to create book archive: {e}")
        if verbose:
            traceback.print_exc()
        sys.exit(1)
