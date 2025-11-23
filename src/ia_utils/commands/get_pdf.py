"""Get PDF command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import ia_client
from ia_utils.utils.logger import Logger
from ia_utils.utils.pages import extract_ia_id


@click.command()
@click.argument('identifier', required=False)
@click.option('-c', '--catalog', type=click.Path(exists=True), help='Load IA ID from catalog database')
@click.option('-a', '--auto', 'auto_filename', is_flag=True, help='Auto-generate filename from slug')
@click.option('-o', '--output', type=str, help='Custom output filename')
@click.pass_context
def get_pdf(ctx, identifier, catalog, auto_filename, output):
    """Download PDF from Internet Archive document.

    IDENTIFIER can be an IA ID or full URL:
    - anatomicalatlasi00smit
    - https://archive.org/details/anatomicalatlasi00smit

    Alternatively, use -c to load IA ID from a catalog database:
    - get-pdf -c catalog.sqlite

    FILENAME MODES:
    - No flags: {id}.pdf
    - -a: {slug}.pdf (from database metadata or auto-generated)
    - -o custom: custom.pdf

    Examples:
        ia-utils get-pdf anatomicalatlasi00smit
        ia-utils get-pdf anatomicalatlasi00smit -a
        ia-utils get-pdf -c catalog.sqlite -a
        ia-utils get-pdf anatomicalatlasi00smit -o my_document.pdf
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Determine IA ID from either identifier arg or catalog database
    if catalog:
        if identifier:
            logger.error("Cannot specify both IDENTIFIER and -c/--catalog")
            sys.exit(1)

        # Load IA ID from catalog database
        if verbose:
            logger.info(f"Loading catalog: {catalog}")

        try:
            db = sqlite_utils.Database(catalog)
            metadata = list(db['document_metadata'].rows_where(limit=1))
            if not metadata:
                logger.error("No metadata found in catalog database")
                sys.exit(1)
            ia_id = metadata[0]['ia_identifier']
            slug = metadata[0].get('slug', '')
        except Exception as e:
            logger.error(f"Failed to read catalog database: {e}")
            sys.exit(1)
    else:
        if not identifier:
            logger.error("Must provide either IDENTIFIER or -c/--catalog")
            sys.exit(1)

        ia_id = extract_ia_id(identifier)
        slug = None

    if verbose:
        logger.section(f"Downloading PDF for: {ia_id}")

    # Download PDF
    pdf_filename = f"{ia_id}.pdf"

    if verbose:
        logger.info(f"1. Downloading PDF...")

    try:
        pdf_bytes = ia_client.download_file(ia_id, pdf_filename, logger=logger, verbose=verbose)
    except Exception:
        sys.exit(1)

    # Determine output filename
    if output:
        # Custom filename
        output_filename = output
        if verbose:
            logger.info(f"2. Using custom filename: {output_filename}")
    elif auto_filename:
        # Auto-generate from slug
        if slug:
            output_filename = f"{slug}.pdf"
            if verbose:
                logger.info(f"2. Auto-generated filename: {output_filename}")
        else:
            output_filename = f"{ia_id}.pdf"
            if verbose:
                logger.info(f"2. Auto-generated filename (from ID): {output_filename}")
    else:
        # Default: use IA ID
        output_filename = f"{ia_id}.pdf"
        if verbose:
            logger.info(f"2. Using filename: {output_filename}")

    # Write PDF to file
    output_path = Path.cwd() / output_filename

    try:
        output_path.write_bytes(pdf_bytes)
        if verbose:
            logger.section("Complete")
            logger.info(f"✓ PDF saved: {output_path}")
        else:
            click.echo(str(output_path))
    except Exception as e:
        logger.error(f"Failed to write PDF: {e}")
        sys.exit(1)
