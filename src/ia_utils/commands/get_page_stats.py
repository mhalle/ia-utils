"""Get page statistics command."""

import sys
from pathlib import Path
import click
import sqlite_utils

from ia_utils.core.database import get_document_metadata
from ia_utils.utils.logger import Logger
from ia_utils.utils.pages import parse_page_range
from ia_utils.utils.output import write_output, determine_format


@click.command('get-page-stats')
@click.option('-c', '--catalog', type=click.Path(exists=True), required=True,
              help='Catalog database path')
@click.option('-l', '--leaf', type=str, help='Leaf range (e.g., 1-7,21,25)')
@click.option('-b', '--book', type=str, help='Book page range (e.g., 100-150)')
@click.option('--output-format', 'output_format',
              type=click.Choice(['table', 'json', 'jsonl', 'csv', 'records']),
              help='Output format (default: table)')
@click.option('-o', '--output', type=click.Path(),
              help='Output file path')
@click.pass_context
def get_page_stats(ctx, catalog, leaf, book, output_format, output):
    """Get per-page statistics from a catalog.

    Returns statistics for each page including block count, line count,
    word count, and non-whitespace character count. Useful for identifying
    pages with figures (typically have fewer text blocks and lower word counts).

    PAGE SELECTION:

    \b
    -l/--leaf     Leaf range (e.g., 1-7,21,25)
    -b/--book     Book page range (e.g., 100-150)
    (omit both)   All pages in catalog

    OUTPUT FIELDS:

    \b
    leaf          Leaf number (physical scan order)
    page          Book page number (if known)
    block_count   Number of text blocks
    line_count    Total lines across blocks
    word_count    Word count (whitespace-separated)
    length        Non-whitespace character count
    avg_confidence  Average OCR confidence (hOCR/djvu catalogs only)

    Examples:
        ia-utils get-page-stats -c catalog.sqlite
        ia-utils get-page-stats -c catalog.sqlite -l 100-150
        ia-utils get-page-stats -c catalog.sqlite --output-format json
        ia-utils get-page-stats -c catalog.sqlite -o stats.csv
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Validate mutually exclusive options
    if leaf and book:
        logger.error("Cannot specify both --leaf and --book")
        sys.exit(1)

    # Load catalog
    try:
        db = sqlite_utils.Database(catalog)
        doc_metadata = get_document_metadata(db)
        if not doc_metadata:
            logger.error("No metadata found in catalog database")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to read catalog database: {e}")
        sys.exit(1)

    # Get all page IDs from catalog
    try:
        all_pages = [row[0] for row in db.execute(
            "SELECT DISTINCT page_id FROM text_blocks ORDER BY page_id"
        ).fetchall()]
    except Exception as e:
        logger.error(f"Failed to query pages: {e}")
        sys.exit(1)

    if not all_pages:
        logger.error("No pages found in catalog")
        sys.exit(1)

    # Determine which pages to include
    if leaf:
        try:
            requested_pages = set(parse_page_range(leaf))
            selected_pages = [p for p in all_pages if p in requested_pages]
        except ValueError as e:
            logger.error(f"Invalid leaf range: {e}")
            sys.exit(1)
    elif book:
        try:
            requested_book_pages = parse_page_range(book)
            # Look up leaf numbers for book pages
            selected_pages = []
            for book_page in requested_book_pages:
                result = db.execute(
                    "SELECT leaf_num FROM page_numbers WHERE book_page_number = ?",
                    [str(book_page)]
                ).fetchone()
                if result:
                    selected_pages.append(result[0])
            selected_pages = [p for p in selected_pages if p in all_pages]
        except ValueError as e:
            logger.error(f"Invalid book page range: {e}")
            sys.exit(1)
    else:
        selected_pages = all_pages

    if not selected_pages:
        logger.error("No matching pages found")
        sys.exit(1)

    # Build query for statistics
    placeholders = ','.join('?' * len(selected_pages))
    query = f"""
        SELECT
            tb.page_id as leaf,
            pn.book_page_number as page,
            COUNT(*) as block_count,
            COALESCE(SUM(tb.line_count), 0) as line_count,
            SUM(tb.length) as length,
            GROUP_CONCAT(tb.text, ' ') as all_text,
            AVG(tb.avg_confidence) as avg_confidence
        FROM text_blocks tb
        LEFT JOIN page_numbers pn ON tb.page_id = pn.leaf_num
        WHERE tb.page_id IN ({placeholders})
        GROUP BY tb.page_id
        ORDER BY tb.page_id
    """

    try:
        rows = db.execute(query, selected_pages).fetchall()
    except Exception as e:
        logger.error(f"Failed to query statistics: {e}")
        sys.exit(1)

    # Build results with computed word count
    results = []
    for row in rows:
        leaf_num, page_num, block_count, line_count, length, all_text, avg_confidence = row
        # Compute word count from concatenated text
        word_count = len(all_text.split()) if all_text else 0
        results.append({
            'leaf': leaf_num,
            'page': page_num or '',
            'block_count': block_count,
            'line_count': line_count,
            'word_count': word_count,
            'length': length or 0,
            'avg_confidence': round(avg_confidence) if avg_confidence is not None else '',
        })

    # Determine output format and path
    output_path = Path(output) if output else None
    fmt = determine_format(output_format, output_path)
    if fmt == 'records' and len(results) > 1:
        fmt = 'table'  # Default to table for multiple results

    # Output
    fields = ['leaf', 'page', 'block_count', 'line_count', 'word_count', 'length', 'avg_confidence']
    write_output(fmt, fields, results, output_path)
