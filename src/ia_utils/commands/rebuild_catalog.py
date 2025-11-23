"""Rebuild catalog command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import database
from ia_utils.utils.logger import Logger


@click.command()
@click.argument('catalog', type=click.Path(exists=True))
@click.pass_context
def rebuild_catalog(ctx, catalog):
    """Rebuild text_blocks and FTS indexes in an existing catalog database.

    Unconditionally rebuilds text_blocks from the source hOCR file (downloaded
    from Internet Archive), then rebuilds text_blocks_fts and pages_fts indexes
    without modifying other tables (document_metadata, archive_files, etc.).

    This is useful after manual edits or schema updates.

    Example:
        ia-utils rebuild-catalog catalog.sqlite
        ia-utils -v rebuild-catalog catalog.sqlite
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
        ia_id = doc_meta['ia_identifier']
    except Exception as e:
        logger.error(f"Failed to read document_metadata: {e}")
        sys.exit(1)

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
