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
    logger = Logger(verbose=verbose)

    ia_id = extract_ia_id(identifier)

    # Auto-slug when not verbose
    if not verbose:
        auto_slug = True

    # Show header when verbose
    if verbose:
        logger.section(f"Building catalog for: {ia_id}")

    # Download files (into memory)
    if verbose:
        logger.subsection("1. Downloading files from Internet Archive...")

    try:
        meta_bytes = ia_client.download_file(ia_id, f"{ia_id}_meta.xml", logger=logger, verbose=verbose)
        files_bytes = ia_client.download_file(ia_id, f"{ia_id}_files.xml", logger=logger, verbose=verbose)
        hocr_bytes = ia_client.download_file(ia_id, f"{ia_id}_hocr.html", logger=logger, verbose=verbose)
    except Exception:
        sys.exit(1)

    # Try to download page numbers mapping
    if verbose:
        logger.progress("   Downloading page numbers mapping...", nl=False)
    page_numbers_data = ia_client.download_json(ia_id, f"{ia_id}_page_numbers.json", logger=logger, verbose=verbose)
    if verbose:
        if page_numbers_data and 'pages' in page_numbers_data:
            logger.progress_done(f"✓ ({len(page_numbers_data['pages'])} pages)")
        else:
            logger.progress_done("(not available)")

    # Parse files
    if verbose:
        logger.subsection("2. Parsing source files...")

    metadata = parser.parse_metadata(meta_bytes)
    if verbose:
        logger.info(f"   Title: {metadata.get('title', 'Unknown')}")

    files = parser.parse_files(files_bytes)
    if verbose:
        logger.info(f"   ✓ {len(files)} file formats")

    blocks_list = parser.parse_hocr(hocr_bytes, logger=logger)
    pages_set = set(block['page_id'] for block in blocks_list)
    if verbose:
        logger.info(f"   ✓ {len(pages_set)} pages")

    # Determine slug and output filename
    if verbose:
        logger.subsection("3. Determining slug...")

    if slug:
        # User specified slug directly with -o
        final_slug = slug
        if verbose:
            logger.info(f"   Using provided slug: {final_slug}")
    elif auto_slug or human_filename:
        # Auto-generate without interaction
        final_slug = generate_slug(metadata, ia_id)
        if verbose:
            logger.info(f"   Auto-generated slug: {final_slug}")
    else:
        # Interactive mode (default)
        suggested_slug = generate_slug(metadata, ia_id)
        logger.info(f"   Suggested slug: {suggested_slug}")
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
            logger=logger
        )
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        sys.exit(1)

    if verbose:
        logger.section(f"Complete")
        logger.info(f"✓ Database created: {output_path}")
        logger.info(f"✓ Slug: {final_slug}")
    else:
        click.echo(output_path)
