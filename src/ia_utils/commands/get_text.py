"""Get OCR text from catalog database."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

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
        # Get aggregated text for page
        sql = """
            SELECT group_concat(text, ' ') as page_text
            FROM text_blocks
            WHERE page_id = ?
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
        sql = """
            SELECT
                tb.hocr_id,
                tb.text,
                tb.block_type,
                tb.avg_confidence,
                pn.book_page_number
            FROM text_blocks tb
            LEFT JOIN page_numbers pn ON tb.page_id = pn.leaf_num
            WHERE tb.page_id = ?
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
@click.option('-c', '--catalog', type=click.Path(exists=True), required=True,
              help='Catalog database path')
@click.option('-l', '--leaf', 'leaf_range', required=True,
              help='Leaf number(s): 42, 1-10, 1,3,5, or 1-5,10,15-20')
@click.option('--blocks', is_flag=True,
              help='Show individual blocks instead of aggregated page text')
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (use -f to select specific fields)')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format')
def get_text(catalog, leaf_range, blocks, fields, output, output_format):
    """Get full OCR text from catalog for specified pages.

    Retrieves the OCR text stored in the catalog database. Use after
    search-catalog to get full text of matching pages.

    LEAF RANGE:

    \b
    Single page:    -l 42
    Range:          -l 1-10
    List:           -l 1,3,5
    Mixed:          -l 1-5,10,15-20

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
    ia-utils get-text -c catalog.sqlite -l 175
    # Get text for page range
    ia-utils get-text -c catalog.sqlite -l 100-110
    # Get individual blocks with confidence scores
    ia-utils get-text -c catalog.sqlite -l 175 --blocks
    # Export to JSON
    ia-utils get-text -c catalog.sqlite -l 175 --output-format json
    # Get just the text field
    ia-utils get-text -c catalog.sqlite -l 175 -f text
    """
    try:
        db = sqlite_utils.Database(catalog)

        # Get IA ID for URLs
        metadata = list(db['document_metadata'].rows_where(limit=1))
        if not metadata:
            click.echo("Error: No metadata found in catalog", err=True)
            sys.exit(1)
        ia_id = metadata[0]['identifier']

        # Parse leaf range
        try:
            leaf_nums = parse_page_range(leaf_range)
        except ValueError as e:
            click.echo(f"Error: Invalid leaf range: {e}", err=True)
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
