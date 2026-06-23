"""Get OCR text from index database."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

from ia_utils.core.database import get_document_metadata
from ia_utils.utils.output import determine_format, write_output
from ia_utils.utils.pages import parse_page_range


def get_page_text(db: sqlite_utils.Database, leaf_nums: List[int], ia_id: str) -> List[Dict[str, Any]]:
    """Get aggregated text for pages.

    Args:
        db: Database connection
        leaf_nums: List of leaf numbers
        ia_id: IA identifier for building URLs

    Returns:
        List of result dictionaries with page text
    """
    results = []
    for leaf in leaf_nums:
        # Get aggregated text for page.
        # CAST normalizes page_id: matches both integer (current schema) and
        # legacy zero-padded TEXT (e.g. '000030') index formats.
        sql = """
            SELECT group_concat(text, ' ') as page_text
            FROM text_blocks
            WHERE CAST(page_id AS INTEGER) = ?
            ORDER BY rowid
        """
        row = db.execute(sql, [leaf]).fetchone()
        text = row[0] if row and row[0] else ''

        # Get page number if available
        page_row = db.execute(
            "SELECT book_page_number FROM page_numbers WHERE leaf_num = ?",
            [leaf]
        ).fetchone()
        page = page_row[0] if page_row else ''

        results.append({
            'leaf': leaf,
            'page': page or '',
            'text': text,
            'url': f"https://archive.org/details/{ia_id}/page/leaf{leaf}"
        })
    return results


def get_block_text(db: sqlite_utils.Database, leaf_nums: List[int], ia_id: str) -> List[Dict[str, Any]]:
    """Get individual blocks for pages.

    Args:
        db: Database connection
        leaf_nums: List of leaf numbers
        ia_id: IA identifier for building URLs

    Returns:
        List of result dictionaries with block details
    """
    results = []
    for leaf in leaf_nums:
        # CAST normalizes page_id (integer current schema vs legacy zero-padded
        # TEXT) for both the join to page_numbers and the page filter.
        sql = """
            SELECT
                tb.hocr_id,
                tb.text,
                tb.block_type,
                tb.avg_confidence,
                pn.book_page_number
            FROM text_blocks tb
            LEFT JOIN page_numbers pn ON CAST(tb.page_id AS INTEGER) = pn.leaf_num
            WHERE CAST(tb.page_id AS INTEGER) = ?
            ORDER BY tb.rowid
        """
        for row in db.execute(sql, [leaf]).fetchall():
            results.append({
                'leaf': leaf,
                'page': row[4] or '',
                'block_id': row[0],
                'block_type': row[2],
                'confidence': row[3],
                'text': row[1],
                'url': f"https://archive.org/details/{ia_id}/page/leaf{leaf}"
            })
    return results


@click.command(name='get-text')
@click.option('-i', '--index', type=click.Path(exists=True), required=True,
              help='Index database path')
@click.option('-l', '--leaf', 'leaf_range',
              help='Leaf number(s): 42, 1-10, 1,3,5, or 1-5,10,15-20')
@click.option('-b', '--book', 'book_range',
              help='Book page number(s): 42, 100-110, 1,3,5 (printed page, requires lookup)')
@click.option('--blocks', is_flag=True,
              help='Show individual blocks instead of aggregated page text')
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (use -f to select specific fields)')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format')
def get_text(index, leaf_range, book_range, blocks, fields, output, output_format):
    """Get full OCR text from index for specified pages.

    Retrieves the OCR text stored in the index database. Use after
    search-index to get full text of matching pages.

    PAGE SELECTION (one required):

    \b
    -l/--leaf   Leaf number(s) - physical scan order (direct)
    -b/--book   Book page number(s) - printed page (requires lookup)

    RANGE SYNTAX (either option):

    \b
    Single page:    42
    Range:          1-10
    List:           1,3,5
    Mixed:          1-5,10,15-20

    OUTPUT FIELDS (page mode, default):

    \b
    leaf    Leaf number
    page    Printed page number (if available)
    text    Full OCR text for the page
    url     Viewer URL

    OUTPUT FIELDS (--blocks mode):

    \b
    leaf        Leaf number
    page        Printed page number
    block_id    hOCR block identifier
    block_type  Block type (ocr_par, ocr_header, etc.)
    confidence  OCR confidence score
    text        Block text
    url         Viewer URL

    EXAMPLES:

    \b
    # Get text for a single page
    ia-utils get-text -i index.sqlite -l 175
    # Get text for page range
    ia-utils get-text -i index.sqlite -l 100-110
    # Get text by printed book page number(s)
    ia-utils get-text -i index.sqlite -b 42
    ia-utils get-text -i index.sqlite -b 100-110
    # Get individual blocks with confidence scores
    ia-utils get-text -i index.sqlite -l 175 --blocks
    # Export to JSON
    ia-utils get-text -i index.sqlite -l 175 --output-format json
    # Get just the text field
    ia-utils get-text -i index.sqlite -l 175 -f text
    """
    try:
        db = sqlite_utils.Database(index)

        # Get IA ID for URLs
        doc_metadata = get_document_metadata(db)
        if not doc_metadata:
            click.echo("Error: No metadata found in index", err=True)
            sys.exit(1)
        ia_id = doc_metadata['identifier']

        # Validate page selection (exactly one of --leaf / --book)
        if leaf_range and book_range:
            click.echo("Error: Cannot specify both --leaf and --book", err=True)
            sys.exit(1)
        if not leaf_range and not book_range:
            click.echo("Error: Page selection required: use -l/--leaf or -b/--book", err=True)
            sys.exit(1)

        # Resolve to leaf numbers
        if leaf_range:
            try:
                leaf_nums = parse_page_range(leaf_range)
            except ValueError as e:
                click.echo(f"Error: Invalid leaf range: {e}", err=True)
                sys.exit(1)
        else:
            try:
                book_pages = parse_page_range(book_range)
            except ValueError as e:
                click.echo(f"Error: Invalid book page range: {e}", err=True)
                sys.exit(1)
            # Look up leaf number for each book page (skip pages with no mapping)
            leaf_nums = []
            for book_page in book_pages:
                row = db.execute(
                    "SELECT leaf_num FROM page_numbers WHERE book_page_number = ?",
                    [str(book_page)]
                ).fetchone()
                if row:
                    leaf_nums.append(row[0])
            if not leaf_nums:
                click.echo(f"Error: No leaves found for book page(s): {book_range}", err=True)
                sys.exit(1)

        # Get text
        if blocks:
            results = get_block_text(db, leaf_nums, ia_id)
            default_fields = ['leaf', 'page', 'block_id', 'block_type', 'confidence', 'text']
        else:
            results = get_page_text(db, leaf_nums, ia_id)
            default_fields = ['leaf', 'page', 'text']

        # Determine output fields
        output_fields = list(fields) if fields else default_fields

        # Determine format
        output_path = Path(output) if output else None
        format_name = determine_format(output_format, output_path)

        write_output(format_name, output_fields, results, output_path)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
