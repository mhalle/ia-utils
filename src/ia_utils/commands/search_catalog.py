"""Search catalog database using FTS."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

from ia_utils.utils.output import determine_format, write_output


DEFAULT_FIELDS = ['leaf', 'page', 'snippet', 'url']


def search_pages(db: sqlite_utils.Database, query: str, limit: int, ia_id: str) -> List[Dict[str, Any]]:
    """Search page-level FTS index.

    Args:
        db: Database connection
        query: FTS5 query string
        limit: Maximum results
        ia_id: IA identifier for building URLs

    Returns:
        List of result dictionaries
    """
    sql = """
        SELECT
            pf.page_id as leaf,
            pn.book_page_number as page,
            snippet(pages_fts, 0, '→', '←', '...', 32) as snippet
        FROM pages_fts pf
        LEFT JOIN page_numbers pn ON pf.page_id = pn.leaf_num
        WHERE pages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    results = []
    for row in db.execute(sql, [query, limit]).fetchall():
        leaf = row[0] or 0
        results.append({
            'leaf': leaf,
            'page': row[1] or '',
            'snippet': row[2],
            'url': f"https://archive.org/details/{ia_id}/page/leaf{leaf}"
        })
    return results


def search_blocks(db: sqlite_utils.Database, query: str, limit: int, ia_id: str) -> List[Dict[str, Any]]:
    """Search block-level FTS index.

    Args:
        db: Database connection
        query: FTS5 query string
        limit: Maximum results
        ia_id: IA identifier for building URLs

    Returns:
        List of result dictionaries
    """
    sql = """
        SELECT
            tb.page_id as leaf,
            pn.book_page_number as page,
            snippet(text_blocks_fts, 0, '→', '←', '...', 32) as snippet
        FROM text_blocks_fts tbf
        JOIN text_blocks tb ON tbf.rowid = tb.rowid
        LEFT JOIN page_numbers pn ON tb.page_id = pn.leaf_num
        WHERE text_blocks_fts MATCH ?
        ORDER BY tbf.rank
        LIMIT ?
    """
    results = []
    for row in db.execute(sql, [query, limit]).fetchall():
        leaf = row[0] or 0
        results.append({
            'leaf': leaf,
            'page': row[1] or '',
            'snippet': row[2],
            'url': f"https://archive.org/details/{ia_id}/page/leaf{leaf}"
        })
    return results


@click.command(name='search-catalog')
@click.option('-c', '--catalog', type=click.Path(exists=True), required=True,
              help='Catalog database path')
@click.option('-q', '--query', required=True, help='Search query (FTS5 syntax)')
@click.option('-l', '--limit', type=int, default=20, show_default=True,
              help='Maximum results')
@click.option('--blocks', is_flag=True, help='Search blocks instead of pages (more granular)')
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (default: leaf, page, snippet, url)')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format')
def search_catalog(catalog, query, limit, blocks, fields, output, output_format):
    """Search catalog database using FTS on OCR text.

    Searches the full-text index built from OCR content. By default searches
    at page level; use --blocks for finer granularity.

    QUERY SYNTAX (FTS5):

    \b
    Simple terms:      femur
    Phrase:            "circle of willis"
    AND (implicit):    femur head
    OR:                femur OR tibia
    NOT:               anatomy NOT surgery
    Prefix:            anat*
    NEAR:              femur NEAR head
    NEAR/N:            femur NEAR/5 head

    OUTPUT FIELDS:

    \b
    leaf      Leaf number (for get-page, get-url)
    page      Printed page number (if available)
    snippet   Text excerpt with →highlights←
    url       Viewer URL (ready to use)

    DIRECT SQL ACCESS:

    For complex queries, use sqlite3 directly:

    \b
    Tables:
      pages_fts       Page-level FTS (page_text, page_id)
      text_blocks     Full block data (text, page_id, bbox, confidence...)
      text_blocks_fts Block-level FTS
      page_numbers    Leaf-to-page mapping

    \b
    Example:
      sqlite3 catalog.sqlite "SELECT page_id, snippet(pages_fts, 0, '>', '<', '...', 20)
        FROM pages_fts WHERE pages_fts MATCH 'femur NEAR head' LIMIT 10"

    EXAMPLES:

    \b
    # Simple search
    ia-utils search-catalog -c catalog.sqlite -q "femur"
    # Phrase search
    ia-utils search-catalog -c catalog.sqlite -q '"circle of willis"'
    # Export to JSON
    ia-utils search-catalog -c catalog.sqlite -q "anatomy" --output-format json
    # Block-level search
    ia-utils search-catalog -c catalog.sqlite -q "nerve" --blocks
    """
    try:
        db = sqlite_utils.Database(catalog)

        # Get IA ID for URLs
        metadata = list(db['document_metadata'].rows_where(limit=1))
        if not metadata:
            click.echo("Error: No metadata found in catalog", err=True)
            sys.exit(1)
        ia_id = metadata[0]['ia_identifier']

        # Search
        if blocks:
            results = search_blocks(db, query, limit, ia_id)
        else:
            results = search_pages(db, query, limit, ia_id)

        # Determine output fields
        output_fields = list(fields) if fields else DEFAULT_FIELDS

        # Determine format
        output_path = Path(output) if output else None
        format_name = determine_format(output_format, output_path)

        write_output(format_name, output_fields, results, output_path)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
