"""Get PDF command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core import ia_client
from ia_utils.core.database import get_document_metadata, get_index_metadata
from ia_utils.utils.logger import Logger
from ia_utils.utils.pages import extract_ia_id


@click.command()
@click.argument('identifier', required=False)
@click.option('-i', '--index', type=click.Path(exists=True), help='Load IA ID from index database')
@click.option('-d', '--dir', 'output_dir', type=click.Path(file_okay=False), help='Output directory')
@click.option('-o', '--output', type=str, help='Override output filename')
@click.pass_context
def get_pdf(ctx, identifier, index, output_dir, output):
    """Download PDF from Internet Archive document.

    IDENTIFIER:
    IA ID or full URL. Can be omitted if using -i/--index.

    OUTPUT:
    With -i/--index: defaults to {slug}.pdf (human-readable name from index)
    Without index: defaults to {ia_id}.pdf
    Use -o to override filename, -d to specify directory.

    EXAMPLES:

    \b
    # Download by ID (saves as {ia_id}.pdf)
    ia-utils get-pdf anatomicalatlasi00smit
    # Download using index (saves as {slug}.pdf)
    ia-utils get-pdf -i index.sqlite
    # Custom filename
    ia-utils get-pdf -i index.sqlite -o anatomy.pdf
    # Save to specific directory
    ia-utils get-pdf -i index.sqlite -d ./pdfs/
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Determine IA ID from either identifier arg or index database
    if index:
        if identifier:
            logger.error("Cannot specify both IDENTIFIER and -i/--index")
            sys.exit(1)

        # Load IA ID from index database
        if verbose:
            logger.info(f"Loading index: {index}")

        try:
            db = sqlite_utils.Database(index)
            doc_metadata = get_document_metadata(db)
            idx_metadata = get_index_metadata(db)
            if not doc_metadata:
                logger.error("No metadata found in index database")
                sys.exit(1)
            ia_id = doc_metadata['identifier']
            slug = idx_metadata.get('slug', '')
        except Exception as e:
            logger.error(f"Failed to read index database: {e}")
            sys.exit(1)
    else:
        if not identifier:
            logger.error("Must provide either IDENTIFIER or -i/--index")
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
        # Use slug from index (human-readable)
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
