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

    # Download common files (into memory)
    if verbose:
        logger.subsection("1. Downloading files from Internet Archive...")

    try:
        meta_bytes = ia_client.download_file(ia_id, f"{ia_id}_meta.xml", logger=logger, verbose=verbose)
        files_bytes = ia_client.download_file(ia_id, f"{ia_id}_files.xml", logger=logger, verbose=verbose)
    except Exception:
        sys.exit(1)

    # Parse files.xml to check available files
    files = parser.parse_files(files_bytes)

    # Determine which mode to use
    if full:
        # Full mode: use hOCR
        blocks_list, pages_list, catalog_mode = download_hocr_mode(
            ia_id, files, logger, verbose
        )
    else:
        # Fast mode: try searchtext, fall back to hOCR if not available
        searchtext_file, pageindex_file = ia_client.get_searchtext_files(ia_id)
        searchtext_available = any(f['filename'] == searchtext_file for f in files)
        pageindex_available = any(f['filename'] == pageindex_file for f in files)

        if searchtext_available and pageindex_available:
            blocks_list, pages_list, catalog_mode = download_searchtext_mode(
                ia_id, searchtext_file, pageindex_file, logger, verbose
            )
        else:
            if verbose:
                logger.warning("   Searchtext files not available, falling back to hOCR...")
            blocks_list, pages_list, catalog_mode = download_hocr_mode(
                ia_id, files, logger, verbose
            )

    # Try to download page numbers mapping
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


def download_searchtext_mode(ia_id, searchtext_file, pageindex_file, logger, verbose):
    """Download and parse searchtext + pageindex for fast mode.

    Returns:
        Tuple of (blocks_list, pages_list, catalog_mode)
    """
    try:
        searchtext_bytes = ia_client.download_gzipped(
            ia_id, searchtext_file, logger=logger, verbose=verbose
        )
        pageindex_bytes = ia_client.download_gzipped(
            ia_id, pageindex_file, logger=logger, verbose=verbose
        )
    except Exception:
        sys.exit(1)

    searchtext_lines = parser.parse_searchtext(searchtext_bytes)
    pageindex = parser.parse_pageindex(pageindex_bytes)

    blocks_list, pages_list = parser.blocks_from_searchtext(
        searchtext_lines, pageindex, logger=logger
    )

    return blocks_list, pages_list, 'searchtext'
