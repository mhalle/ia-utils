"""Get pages command for batch page downloads."""

import sys
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED
import click
import sqlite_utils

from ia_utils.core import image, ia_client
from ia_utils.core.database import get_document_metadata, get_index_metadata
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils
from ia_utils.utils.pages import parse_page_range


@click.command()
@click.argument('identifier', required=False)
@click.option('-l', '--leaf', type=str, help='Leaf range (e.g., 1-7,21,25,-10,200-)')
@click.option('-b', '--book', type=str, help='Book page range (e.g., 100-150,-20,200-)')
@click.option('--all', 'download_all', is_flag=True,
              help='Download all pages')
@click.option('-p', '--prefix', type=str,
              help='Output filename prefix (required for individual files)')
@click.option('-o', '--output', type=str,
              help='Output ZIP filename (for --zip mode)')
@click.option('-i', '--index', type=click.Path(exists=True),
              help='Index database path for page lookups and auto-naming')
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
@click.option('-j', '--jobs', type=int, default=16,
              help='Concurrent downloads (default: 16)')
@click.option('--mosaic', 'as_mosaic', is_flag=True,
              help='Output as mosaic grid image for LLM vision')
@click.option('--width', type=int, default=1536,
              help='Mosaic output width in pixels (default: 1536)')
@click.option('--cols', type=int, default=12,
              help='Mosaic columns (default: 12)')
@click.option('--label', type=click.Choice(['leaf', 'book', 'none']),
              default='leaf', help='Mosaic label type (default: leaf)')
@click.option('--grid', is_flag=True,
              help='Draw grid lines between mosaic tiles')
@click.pass_context
def get_pages(ctx, identifier, leaf, book, download_all, prefix, output, index,
              as_zip, size, format, quality, autocontrast, cutoff, preserve_tone,
              skip_existing, jobs, as_mosaic, width, cols, label, grid):
    """Download page images from Internet Archive.

    IDENTIFIER (optional if -i provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - Omit if using -i (index contains IA ID)

    PAGE SELECTION (one required):

    \b
    -l/--leaf     Leaf range (e.g., 1-7,21,25,-10,200-,1-100:10)
    -b/--book     Book page range (e.g., 100-150,-20,200-)
    --all         All pages (requires -i or fetches metadata)

    Range syntax: -10 means 1-10, 200- means 200 to end, 1-100:10 means every 10th

    OUTPUT MODES:

    \b
    Individual files (default):
      -p prefix     Output as prefix_0001.jpg, prefix_0002.jpg, etc.
    ZIP archive:
      --zip         Output as ZIP file
      -o file.zip   ZIP filename (auto-named for --all --zip)
    Mosaic (for LLM vision):
      --mosaic      Output as single grid image
      -o file.jpg   Mosaic output file

    MOSAIC OPTIONS:

    \b
    --width N     Output width in pixels (default: 1536)
    --cols N      Number of columns (default: 12)
    --label TYPE  Label tiles: leaf, book, none (default: leaf)
    --grid        Draw grid lines between tiles

    IMAGE SIZES:

    \b
    small     ~300px width (very fast, used for mosaic)
    medium    ~600px width (default)
    large     full resolution
    original  full resolution JP2 lossless (individual files only)

    EXAMPLES:

    \b
    # Download range as individual files
    ia-utils get-pages -i book.sqlite -l 1-7 -p pages/atlas
    # Download all pages as ZIP (auto-named)
    ia-utils get-pages -i book.sqlite --all --zip
    # Create mosaic of pages 1-50
    ia-utils get-pages -i book.sqlite -l 1-50 --mosaic -o overview.jpg
    # Mosaic with every 10th page
    ia-utils get-pages -i book.sqlite -l 0-:10 --mosaic -o sampled.jpg
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID from identifier (if provided)
    ia_id = None
    slug = None
    if identifier:
        ia_id = page_utils.extract_ia_id(identifier)

    # Load index if provided
    db = None
    total_pages = None
    max_page = None  # Max leaf number for open-ended ranges
    all_page_ids = None  # Actual leaf numbers from index
    if index:
        if verbose:
            logger.info(f"Loading index: {index}")
        try:
            db = sqlite_utils.Database(index)
            doc_metadata = get_document_metadata(db)
            idx_metadata = get_index_metadata(db)
            if not doc_metadata:
                logger.error("No metadata found in index database")
                sys.exit(1)
            ia_id_from_index = doc_metadata['identifier']
            slug = idx_metadata.get('slug', '')
            # Verify IA ID matches if identifier was also provided
            if ia_id and ia_id != ia_id_from_index:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Index: {ia_id_from_index}")
                sys.exit(1)
            ia_id = ia_id_from_index

            # Get page IDs from index for --all mode and open-ended ranges
            try:
                pages_rows = list(db.execute("SELECT DISTINCT page_id FROM text_blocks ORDER BY page_id").fetchall())
                all_page_ids = [row[0] for row in pages_rows]
                total_pages = len(all_page_ids)
                max_page = max(all_page_ids) if all_page_ids else None
                if verbose and download_all:
                    logger.info(f"Found {total_pages} pages in index (leaf range: {min(all_page_ids)}-{max(all_page_ids)})")
            except Exception:
                all_page_ids = None
        except Exception as e:
            logger.error(f"Failed to read index database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("IDENTIFIER required (or use -i with index)")
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
    if as_zip and as_mosaic:
        logger.error("Cannot combine --zip and --mosaic")
        sys.exit(1)

    if as_mosaic:
        # Mosaic mode validations
        if size == 'original':
            logger.error("--mosaic mode does not support --size original")
            sys.exit(1)
        if any([autocontrast, cutoff, preserve_tone, quality]):
            logger.error("--mosaic mode does not support image processing options")
            sys.exit(1)
        if prefix:
            logger.error("Use -o/--output for mosaic filename, not -p/--prefix")
            sys.exit(1)
        if not output:
            logger.error("--mosaic requires -o/--output for output file")
            sys.exit(1)
    elif as_zip:
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
            logger.error("-o/--output is for --zip/--mosaic mode; use -p/--prefix for individual files")
            sys.exit(1)

    # Get total pages for --all mode
    if download_all:
        if all_page_ids is not None:
            # Use actual page IDs from index (handles leaf0, non-contiguous pages)
            pages = all_page_ids
        elif total_pages is None:
            # Fetch from IA metadata - use range starting at 0 (leaf0 is valid)
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

            # Leaf numbers are 0-indexed (leaf0 through leaf{n-1})
            pages = list(range(0, total_pages))
        else:
            # Shouldn't happen, but fallback
            pages = list(range(0, total_pages))

        num_type = 'leaf'
    elif leaf:
        try:
            pages = parse_page_range(leaf, max_page=max_page)
        except ValueError as e:
            logger.error(f"Invalid leaf range: {e}")
            sys.exit(1)
        num_type = 'leaf'
    else:  # book
        # Handle open-ended book page ranges specially (e.g., "200-")
        # Convert start page to leaf, then take all leaves to end
        if book.strip().endswith('-') and not book.strip().startswith('-'):
            try:
                start_book_page = int(book.strip()[:-1])
                start_leaf = page_utils.get_leaf_num(start_book_page, 'book', ia_id=ia_id, db=db)
                if max_page is None:
                    raise ValueError("Open-ended range requires -i/--index")
                pages = list(range(start_leaf, max_page + 1))
                num_type = 'leaf'  # Now working with leaves
                if verbose:
                    logger.info(f"Book page {start_book_page} -> leaf {start_leaf}, taking leaves {start_leaf}-{max_page}")
            except ValueError as e:
                logger.error(f"Invalid book page range: {e}")
                sys.exit(1)
        else:
            try:
                pages = parse_page_range(book, max_page=None)
            except ValueError as e:
                logger.error(f"Invalid book page range: {e}")
                sys.exit(1)
            num_type = 'book'

    # Handle mosaic output mode
    if as_mosaic:
        _download_as_mosaic(
            ia_id=ia_id,
            pages=pages,
            num_type=num_type,
            output=output,
            width=width,
            cols=cols,
            label=label,
            grid=grid,
            jobs=jobs,
            db=db,
            logger=logger,
            verbose=verbose
        )
        return

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


def _download_as_mosaic(ia_id, pages, num_type, output, width, cols, label,
                         grid, jobs, db, logger, verbose):
    """Download pages and create a mosaic grid image."""
    output_path = Path(output)

    if verbose:
        logger.section(f"Creating mosaic from {len(pages)} pages: {ia_id}")
        logger.info(f"   Output: {output_path}")
        logger.info(f"   Width: {width}px, Columns: {cols}")
        logger.info(f"   Labels: {label}")

    # Convert book pages to leaf numbers if needed, keeping track of original page nums for labels
    leaf_nums = []
    page_labels = []  # Original page numbers for labels

    for page_num in pages:
        try:
            leaf_num = page_utils.get_leaf_num(page_num, num_type, ia_id=ia_id, db=db)
            leaf_nums.append(leaf_num)
            page_labels.append(page_num)
        except ValueError as e:
            logger.error(f"Page {page_num}: {e}")

    if not leaf_nums:
        logger.error("No valid pages to download")
        sys.exit(1)

    # Choose image size based on tile width
    tile_width = width // cols
    if tile_width >= 600:
        img_size = 'large'
    elif tile_width >= 250:
        img_size = 'medium'
    else:
        img_size = 'small'

    try:
        if verbose:
            logger.subsection(f"\nDownloading {len(leaf_nums)} pages ({img_size} images)...")

        results = ia_client.download_images(ia_id, leaf_nums, size=img_size, max_concurrent=jobs)

        # Create lookup by leaf number
        image_data = {}
        for fname, data in results:
            # Extract leaf number from filename like "id_0042.jpg"
            leaf = int(fname.split('_')[-1].split('.')[0])
            image_data[leaf] = data

        # Collect images in order
        images = []
        labels = []
        for idx, leaf_num in enumerate(leaf_nums):
            if leaf_num in image_data:
                images.append(image_data[leaf_num])
                # Generate label based on label type
                if label == 'leaf':
                    labels.append(str(leaf_num))
                elif label == 'book':
                    labels.append(str(page_labels[idx]))
                else:
                    labels.append('')

        if verbose:
            logger.subsection(f"\nCreating mosaic...")

        # Create mosaic
        mosaic = image.create_mosaic(
            images=images,
            labels=labels if label != 'none' else None,
            width=width,
            cols=cols,
            grid=grid
        )

        # Save mosaic
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mosaic.save(output_path, quality=90)

        if verbose:
            size_mb = output_path.stat().st_size / 1024 / 1024
            logger.section("Complete")
            logger.info(f"✓ Mosaic created: {output_path}")
            logger.info(f"✓ Size: {size_mb:.1f} MB ({mosaic.width}x{mosaic.height}px)")
            logger.info(f"✓ Pages: {len(images)}")
        else:
            click.echo(str(output_path))

    except Exception as e:
        import traceback
        logger.error(f"Failed to create mosaic: {e}")
        if verbose:
            traceback.print_exc()
        sys.exit(1)


def _download_as_zip(ia_id, slug, pages, num_type, output, download_all, size,
                     jobs, db, logger, verbose):
    """Download pages as a ZIP archive with parallel async downloads."""
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
        logger.info(f"   Concurrent downloads: {jobs}")

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

    # Download all pages in parallel using async httpx
    try:
        if verbose:
            logger.subsection(f"\nDownloading {len(pages)} pages...")

        results = ia_client.download_images(ia_id, pages, size=size, max_concurrent=jobs)

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
    """Download pages as individual files with parallel downloads."""
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

    # For 'original' size (JP2), fall back to sequential downloads
    if size == 'original':
        _download_individual_files_sequential(
            ia_id, pages, num_type, prefix, size, output_format,
            quality, autocontrast, cutoff, preserve_tone,
            skip_existing, db, logger, verbose
        )
        return

    # Convert page numbers to leaf numbers and filter existing
    download_tasks = []  # List of (page_num, leaf_num, output_path)
    skipped = 0

    for page_num in pages:
        try:
            leaf_num = page_utils.get_leaf_num(page_num, num_type, ia_id=ia_id, db=db)
        except ValueError as e:
            logger.error(f"Page {page_num}: {e}")
            continue

        output_filename = f"{prefix}_{page_num:04d}.{output_format}"
        output_path = Path(output_filename)

        if skip_existing and output_path.exists():
            if verbose:
                logger.progress(f"   Skipping {output_path.name} (exists)")
            skipped += 1
            continue

        download_tasks.append((page_num, leaf_num, output_path))

    if not download_tasks:
        if verbose:
            logger.section("Complete")
            logger.info(f"✓ Skipped: {skipped} (all exist)")
        else:
            click.echo(f"0/{len(pages)} pages downloaded, {skipped} skipped")
        return

    # Download all images in parallel
    try:
        leaf_nums = [t[1] for t in download_tasks]

        if verbose:
            logger.subsection(f"\nDownloading {len(download_tasks)} pages...")

        results = ia_client.download_images(ia_id, leaf_nums, size=size)

        # Create lookup by leaf number
        image_data = {leaf: data for leaf, data in
                      [(int(fname.split('_')[-1].split('.')[0]), data)
                       for fname, data in results]}

        if verbose:
            logger.subsection(f"\nSaving {len(download_tasks)} files...")

        # Process and save each image
        successful = 0
        failed = 0
        needs_processing = autocontrast or cutoff is not None or preserve_tone

        for idx, (page_num, leaf_num, output_path) in enumerate(download_tasks, 1):
            try:
                img_bytes = image_data.get(leaf_num)
                if img_bytes is None:
                    logger.error(f"Page {page_num}: No data received")
                    failed += 1
                    continue

                if needs_processing or output_format != 'jpg':
                    # Need to process through PIL
                    image.process_image(
                        img_bytes,
                        output_path,
                        output_format=output_format,
                        quality=quality,
                        autocontrast=autocontrast,
                        cutoff=cutoff,
                        preserve_tone=preserve_tone,
                        logger=logger if verbose else None
                    )
                else:
                    # Fast path: just write bytes
                    output_path.write_bytes(img_bytes)

                if verbose:
                    logger.progress(f"   [{idx}/{len(download_tasks)}] Saved {output_path.name}")
                successful += 1

            except Exception as e:
                if verbose:
                    logger.error(f"   [{idx}/{len(download_tasks)}] {output_path.name}: {e}")
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


def _download_individual_files_sequential(ia_id, pages, num_type, prefix, size, output_format,
                                          quality, autocontrast, cutoff, preserve_tone,
                                          skip_existing, db, logger, verbose):
    """Sequential fallback for original size downloads."""
    successful = 0
    failed = 0
    skipped = 0

    if verbose:
        logger.subsection(f"\nDownloading {len(pages)} pages (sequential)...")

    for idx, page_num in enumerate(pages, 1):
        try:
            try:
                leaf_num = page_utils.get_leaf_num(page_num, num_type, ia_id=ia_id, db=db)
            except ValueError as e:
                logger.error(f"Page {page_num}: {e}")
                failed += 1
                continue

            output_filename = f"{prefix}_{page_num:04d}.{output_format}"
            output_path = Path(output_filename)

            if skip_existing and output_path.exists():
                if verbose:
                    logger.progress(f"  [{idx}/{len(pages)}] Skipping {output_path.name} (exists)")
                skipped += 1
                continue

            if verbose:
                logger.progress(f"  [{idx}/{len(pages)}] leaf {leaf_num}...", nl=False)

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
