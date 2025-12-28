"""Rebuild catalog command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import ia_client, parser, database
from ia_utils.utils.logger import Logger
from ia_utils.utils.slug import generate_slug


@click.command()
@click.argument('catalog', type=click.Path(exists=True))
@click.option('--full', is_flag=True,
              help='Fully regenerate catalog including metadata (re-downloads all files).')
@click.pass_context
def rebuild_catalog(ctx, catalog, full):
    """Rebuild text_blocks and FTS indexes in an existing catalog database.

    By default, rebuilds text_blocks from the source hOCR file (downloaded
    from Internet Archive), then rebuilds FTS indexes without modifying
    other tables (document_metadata, archive_files, etc.).

    Use --full to completely regenerate the catalog, including metadata.
    This is useful after schema changes that add new metadata fields.

    Examples:
        ia-utils rebuild-catalog catalog.sqlite
        ia-utils rebuild-catalog catalog.sqlite --full
        ia-utils -v rebuild-catalog catalog.sqlite --full
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    try:
        db = sqlite_utils.Database(catalog)
    except Exception as e:
        logger.error(f"Failed to open catalog: {e}")
        sys.exit(1)

    # Verify required tables exist
    try:
        tables = {t.name for t in db.tables}
        if 'document_metadata' not in tables:
            logger.error("Catalog must have document_metadata table")
            sys.exit(1)
        if 'archive_files' not in tables:
            logger.error("Catalog must have archive_files table")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to verify catalog structure: {e}")
        sys.exit(1)

    # Get document metadata
    try:
        doc_meta = list(db['document_metadata'].rows_where(limit=1))[0]
        ia_id = doc_meta['identifier']
    except Exception as e:
        logger.error(f"Failed to read document_metadata: {e}")
        sys.exit(1)

    # Full regeneration mode
    if full:
        catalog_path = Path(catalog)
        if verbose:
            logger.section(f"Full regeneration: {catalog}")
            logger.info(f"IA identifier: {ia_id}")
            logger.subsection("1. Downloading files from Internet Archive...")

        try:
            meta_bytes = ia_client.download_file(ia_id, f"{ia_id}_meta.xml", logger=logger, verbose=verbose)
            files_bytes = ia_client.download_file(ia_id, f"{ia_id}_files.xml", logger=logger, verbose=verbose)
        except Exception:
            sys.exit(1)

        # Parse files.xml to find actual hOCR filename (may differ from standard naming)
        files = parser.parse_files(files_bytes)
        hocr_candidates = [f['filename'] for f in files if f['filename'].endswith('_hocr.html')]
        if not hocr_candidates:
            logger.error(f"No hOCR file found for {ia_id}")
            sys.exit(1)
        hocr_filename = hocr_candidates[0]

        try:
            hocr_bytes = ia_client.download_file(ia_id, hocr_filename, logger=logger, verbose=verbose)
        except Exception:
            sys.exit(1)

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

        if verbose:
            logger.subsection("2. Parsing source files...")

        metadata = parser.parse_metadata(meta_bytes)
        title = next((v for k, v in metadata if k == 'title'), 'Unknown')
        if verbose:
            logger.info(f"   Title: {title}")
            logger.info(f"   ✓ {len(files)} file formats")

        blocks_list = parser.parse_hocr(hocr_bytes, logger=logger)
        pages_set = set(block['page_id'] for block in blocks_list)
        if verbose:
            logger.info(f"   ✓ {len(pages_set)} pages")

        if verbose:
            logger.subsection("3. Generating slug...")
        final_slug = generate_slug(metadata, ia_id)
        if verbose:
            logger.info(f"   Slug: {final_slug}")

        if verbose:
            logger.subsection("4. Rebuilding database...")

        # Remove old file and create new one
        catalog_path.unlink()
        try:
            database.create_catalog_database(
                catalog_path,
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
            logger.section("Complete")
            logger.info(f"✓ Catalog regenerated: {catalog_path}")
        else:
            click.echo(str(catalog_path))
        return

    # Find hOCR file in archive_files
    try:
        hocr_file = list(db.execute(
            "SELECT filename FROM archive_files WHERE filename LIKE ?",
            [f"{ia_id}_hocr.html"]
        ).fetchall())
        if not hocr_file:
            logger.error(f"Cannot find hOCR file for {ia_id}")
            sys.exit(1)
        hocr_filename = hocr_file[0][0]
    except Exception as e:
        logger.error(f"Failed to look up hOCR file: {e}")
        sys.exit(1)

    if verbose:
        logger.section(f"Rebuilding catalog: {catalog}")

    try:
        if verbose:
            logger.subsection("1. Building text_blocks...")
        database.rebuild_text_blocks(db, ia_id, hocr_filename, logger=logger)

        if verbose:
            logger.subsection("2. Building FTS indexes...")
        else:
            logger.progress("Building FTS indexes...", nl=False)
        database.build_fts_indexes(db)
        if not verbose:
            logger.progress_done("✓")

        if verbose:
            logger.subsection("3. Vacuuming database...")
        else:
            logger.progress("Vacuuming database...", nl=False)
        db.execute("VACUUM;")
        if not verbose:
            logger.progress_done("✓")

        # Get final size and stats
        catalog_path = Path(catalog)
        size_mb = catalog_path.stat().st_size / 1024 / 1024

        if verbose:
            logger.section("Complete")
            logger.info(f"✓ Catalog rebuilt: {catalog_path}")
            logger.info(f"✓ Size: {size_mb:.1f} MB")
        else:
            click.echo(str(catalog_path))

    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        sys.exit(1)
