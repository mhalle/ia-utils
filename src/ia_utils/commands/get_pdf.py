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
@click.option('-d', '--dir', 'output_dir', type=click.Path(file_okay=False), help='Output directory')
@click.option('-o', '--output', type=str, help='Override output filename')
@click.pass_context
def get_pdf(ctx, identifier, catalog, output_dir, output):
    """Download PDF from Internet Archive document.

    IDENTIFIER:
    IA ID or full URL. Can be omitted if using -c/--catalog.

    OUTPUT:
    With -c/--catalog: defaults to {slug}.pdf (human-readable name from catalog)
    Without catalog: defaults to {ia_id}.pdf
    Use -o to override filename, -d to specify directory.

    EXAMPLES:

    \b
    # Download by ID (saves as {ia_id}.pdf)
    ia-utils get-pdf anatomicalatlasi00smit
    # Download using catalog (saves as {slug}.pdf)
    ia-utils get-pdf -c catalog.sqlite
    # Custom filename
    ia-utils get-pdf -c catalog.sqlite -o anatomy.pdf
    # Save to specific directory
    ia-utils get-pdf -c catalog.sqlite -d ./pdfs/
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
            ia_id = metadata[0]['identifier']
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
        output_filename = output if output.endswith('.pdf') else f"{output}.pdf"
    elif slug:
        # Use slug from catalog (human-readable)
        output_filename = f"{slug}.pdf"
    else:
        # Fallback to IA ID
        output_filename = f"{ia_id}.pdf"

    # Determine output path
    if output_dir:
        output_path = Path(output_dir) / output_filename
    else:
        output_path = Path.cwd() / output_filename

    if verbose:
        logger.info(f"2. Output: {output_path}")

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
