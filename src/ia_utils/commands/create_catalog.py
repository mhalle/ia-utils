"""Create catalog command."""

import sys
from pathlib import Path

import click

from ia_utils.core import ia_client, parser, database
from ia_utils.utils.logger import Logger
from ia_utils.utils.slug import generate_slug


def extract_ia_id(input_str: str) -> str:
    """Extract IA ID from URL or return as-is if already an ID."""
    if input_str.startswith('http'):
        # Parse URL: https://archive.org/details/IDENTIFIER
        if '/details/' in input_str:
            return input_str.split('/details/')[-1].split('/')[0]
    return input_str


@click.command()
@click.argument('identifier')
@click.option('-d', '--dir', 'output_dir', type=click.Path(file_okay=False),
              help='Output directory (default: current directory)')
@click.option('-o', '--output', type=str, help='Override output filename')
@click.option('--full', is_flag=True, default=False,
              help='Download full hOCR for complete metadata (slower)')
@click.pass_context
def create_catalog(ctx, identifier, output_dir, output, full):
    """Create a catalog database from an Internet Archive document.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    By default, uses fast searchtext mode (text-only, smaller download).
    Use --full to download complete hOCR with bounding boxes, confidence, etc.

    OUTPUT:
    - Default filename: {author}-{title}-{year}_{ia_id}.sqlite
    - Use -o to override filename
    - Use -d to specify output directory

    Examples:
        ia-utils create-catalog anatomicalatlasi00smit
        ia-utils create-catalog anatomicalatlasi00smit --full
        ia-utils create-catalog anatomicalatlasi00smit -d ./catalogs/
        ia-utils create-catalog anatomicalatlasi00smit -o anatomy.sqlite
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    ia_id = extract_ia_id(identifier)

    # Show header when verbose
    if verbose:
        mode_str = "full (hOCR)" if full else "fast (searchtext)"
        logger.section(f"Building catalog for: {ia_id} [{mode_str}]")

    if verbose:
        logger.subsection("1. Downloading files from Internet Archive...")

    if full:
        # Full mode: download metadata first, then hOCR
        if verbose:
            logger.progress("   Downloading metadata files...", nl=False)
        try:
            meta_bytes = ia_client.download_file_direct(ia_id, f"{ia_id}_meta.xml")
            files_bytes = ia_client.download_file_direct(ia_id, f"{ia_id}_files.xml")
            if verbose:
                logger.progress_done("✓")
        except Exception as e:
            if verbose:
                logger.progress_fail("✗")
            logger.error(f"Failed to download metadata: {e}")
            sys.exit(1)

        files = parser.parse_files(files_bytes)
        blocks_list, pages_list, catalog_mode = download_hocr_mode(
            ia_id, files, logger, verbose
        )
        page_numbers_data = None
    else:
        # Fast mode: download ALL files in parallel
        blocks_list, pages_list, page_numbers_data, meta_bytes, files_bytes, catalog_mode = \
            download_fast_mode(ia_id, logger, verbose)

        if catalog_mode == 'fallback_djvu':
            # Searchtext not available, try DjVu XML
            if verbose:
                logger.warning("   Searchtext not available, trying DjVu XML...")
            blocks_list, pages_list, catalog_mode = download_djvu_mode(
                ia_id, logger, verbose
            )
            if catalog_mode == 'fallback_hocr':
                # DjVu XML also not available, fall back to hOCR
                if verbose:
                    logger.warning("   DjVu XML not available, falling back to hOCR...")
                files = parser.parse_files(files_bytes)
                blocks_list, pages_list, catalog_mode = download_hocr_mode(
                    ia_id, files, logger, verbose
                )
                page_numbers_data = None
            else:
                files = parser.parse_files(files_bytes)
        else:
            # Fast mode succeeded, parse files for later use
            files = parser.parse_files(files_bytes)

    # For hOCR mode, download page numbers separately (files already parsed above)
    if catalog_mode == 'hocr':
        if verbose:
            logger.progress("   Downloading page numbers mapping...", nl=False)
        pn_candidates = [f['filename'] for f in files if f['filename'].endswith('_page_numbers.json')]
        page_numbers_data = None
        if pn_candidates:
            page_numbers_data = ia_client.download_json(ia_id, pn_candidates[0], logger=logger, verbose=False)
        if verbose:
            if page_numbers_data and 'pages' in page_numbers_data:
                logger.progress_done(f"✓ ({len(page_numbers_data['pages'])} pages)")
            else:
                logger.progress_done("(not available)")

    # Parse metadata
    if verbose:
        logger.subsection("2. Parsing metadata...")

    metadata = parser.parse_metadata(meta_bytes)
    # Get title from metadata tuples for display
    title = next((v for k, v in metadata if k == 'title'), 'Unknown')
    if verbose:
        logger.info(f"   Title: {title}")
        logger.info(f"   ✓ {len(files)} file formats")

    pages_set = set(block['page_id'] for block in blocks_list)
    if verbose:
        logger.info(f"   ✓ {len(pages_set)} pages, {len(blocks_list)} blocks")

    # Generate slug (always auto-generated, used for filename and stored in DB)
    if verbose:
        logger.subsection("3. Generating slug...")

    final_slug = generate_slug(metadata, ia_id)
    if verbose:
        logger.info(f"   Slug: {final_slug}")

    # Determine output path
    if output:
        output_filename = output if output.endswith('.sqlite') else f"{output}.sqlite"
    else:
        output_filename = f"{final_slug}.sqlite"

    if output_dir:
        output_path = Path(output_dir) / output_filename
    else:
        output_path = Path.cwd() / output_filename

    if verbose:
        logger.subsection("4. Building database...")

    try:
        database.create_catalog_database(
            output_path,
            ia_id,
            final_slug,
            metadata,
            files,
            blocks_list,
            page_numbers_data,
            catalog_mode=catalog_mode,
            pages=pages_list,
            logger=logger
        )
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        sys.exit(1)

    if verbose:
        logger.section("Complete")
        logger.info(f"✓ Database created: {output_path}")
        logger.info(f"✓ Mode: {catalog_mode}")
    else:
        click.echo(output_path)


def download_hocr_mode(ia_id, files, logger, verbose):
    """Download and parse hOCR file for full metadata.

    Returns:
        Tuple of (blocks_list, pages_list, catalog_mode)
    """
    # Find hOCR filename
    hocr_candidates = [f['filename'] for f in files if f['filename'].endswith('_hocr.html')]
    if not hocr_candidates:
        logger.error(f"No hOCR file found for {ia_id}")
        sys.exit(1)
    hocr_filename = hocr_candidates[0]

    try:
        hocr_bytes = ia_client.download_file(ia_id, hocr_filename, logger=logger, verbose=verbose)
    except Exception:
        sys.exit(1)

    blocks_list = parser.parse_hocr(hocr_bytes, logger=logger)

    # No pages table for hOCR mode (blocks have full metadata)
    return blocks_list, None, 'hocr'


def download_djvu_mode(ia_id, logger, verbose):
    """Download and parse DjVu XML file.

    Tries multiple filename patterns:
    - {ia_id}_djvu.xml (standard)
    - {ia_id}_djvuxml.xml (variant)
    - {ia_id}_access_djvu.xml (variant)

    Returns:
        Tuple of (blocks_list, pages_list, catalog_mode)
        If DjVu XML unavailable, catalog_mode='fallback_hocr' and blocks_list is None.
    """
    djvu_patterns = [
        f"{ia_id}_djvu.xml",
        f"{ia_id}_djvuxml.xml",
        f"{ia_id}_access_djvu.xml",
    ]

    djvu_bytes = None
    djvu_filename = None

    for pattern in djvu_patterns:
        if verbose:
            logger.progress(f"   Trying {pattern}...", nl=False)
        try:
            djvu_bytes = ia_client.download_file_direct(ia_id, pattern)
            djvu_filename = pattern
            if verbose:
                size_mb = len(djvu_bytes) / 1024 / 1024
                logger.progress_done(f"✓ ({size_mb:.1f} MB)")
            break
        except Exception:
            if verbose:
                logger.progress_fail("✗")

    if djvu_bytes is None:
        return None, None, 'fallback_hocr'

    blocks_list = parser.parse_djvu_xml(djvu_bytes, logger=logger)

    # No pages table for DjVu mode (similar to hOCR)
    return blocks_list, None, 'djvu'


def download_fast_mode(ia_id, logger, verbose):
    """Download all files in parallel for fast mode.

    Downloads meta.xml, files.xml, searchtext, pageindex, and page_numbers
    all in parallel. If searchtext files aren't available, signals fallback.

    Returns:
        Tuple of (blocks_list, pages_list, page_numbers_data, meta_bytes, files_bytes, catalog_mode)
        If searchtext unavailable, catalog_mode='fallback_hocr' and blocks_list/pages_list are None.
    """
    if verbose:
        logger.progress("   Downloading all files (parallel)...", nl=False)

    searchtext_file, pageindex_file = ia_client.get_searchtext_files(ia_id)

    downloads = [
        {'key': 'meta', 'filename': f"{ia_id}_meta.xml"},
        {'key': 'files', 'filename': f"{ia_id}_files.xml"},
        {'key': 'searchtext', 'filename': searchtext_file, 'gzipped': True, 'optional': True},
        {'key': 'pageindex', 'filename': pageindex_file, 'gzipped': True, 'optional': True},
        {'key': 'page_numbers', 'filename': f"{ia_id}_page_numbers.json", 'json': True, 'optional': True},
    ]

    try:
        results = ia_client.download_parallel(ia_id, downloads, logger=logger, verbose=False)
    except Exception as e:
        if verbose:
            logger.progress_fail("✗")
        logger.error(f"Download failed: {e}")
        sys.exit(1)

    if verbose:
        logger.progress_done("✓")

    meta_bytes = results['meta']
    files_bytes = results['files']

    # Check if searchtext files were available
    if results.get('searchtext') is None or results.get('pageindex') is None:
        return None, None, None, meta_bytes, files_bytes, 'fallback_djvu'

    searchtext_content = parser.parse_searchtext(results['searchtext'])
    pageindex = parser.parse_pageindex(results['pageindex'])
    page_numbers_data = results.get('page_numbers')

    blocks_list, pages_list = parser.blocks_from_searchtext(
        searchtext_content, pageindex, logger=logger
    )

    return blocks_list, pages_list, page_numbers_data, meta_bytes, files_bytes, 'searchtext'
