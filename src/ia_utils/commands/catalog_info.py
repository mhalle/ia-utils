"""Display metadata about catalog databases."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

from ia_utils.utils.output import determine_format, write_output


DEFAULT_FIELDS = [
    'filename',
    'ia_identifier',
    'title',
    'creator_primary',
    'publication_date',
    'page_count',
    'block_count',
    'size_mb',
]


def get_catalog_info(catalog_path: Path) -> Dict[str, Any]:
    """Extract metadata from a catalog database.

    Args:
        catalog_path: Path to the SQLite catalog file

    Returns:
        Dictionary with catalog metadata
    """
    try:
        db = sqlite_utils.Database(catalog_path)

        # Get document metadata
        metadata = list(db['document_metadata'].rows_where(limit=1))
        if not metadata:
            return {'filename': catalog_path.name, 'error': 'No metadata found'}

        meta = metadata[0]

        # Get block count
        block_count = db['text_blocks'].count if 'text_blocks' in db.table_names() else 0

        # Get file size
        size_mb = catalog_path.stat().st_size / 1024 / 1024

        return {
            'filename': catalog_path.name,
            'path': str(catalog_path),
            'ia_identifier': meta.get('ia_identifier', ''),
            'slug': meta.get('slug', ''),
            'title': meta.get('title', ''),
            'creator_primary': meta.get('creator_primary', ''),
            'creator_secondary': meta.get('creator_secondary', ''),
            'publisher': meta.get('publisher', ''),
            'publication_date': meta.get('publication_date', ''),
            'page_count': meta.get('page_count', 0),
            'block_count': block_count,
            'size_mb': round(size_mb, 2),
            'language': meta.get('language', ''),
            'collection': meta.get('collection', ''),
            'description': meta.get('description', ''),
            'created_at': meta.get('created_at', ''),
        }
    except Exception as e:
        return {'filename': catalog_path.name, 'error': str(e)}


@click.command('catalog-info')
@click.argument('catalogs', nargs=-1, type=click.Path(exists=True))
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (repeatable). Use "*" for all fields.')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file (format inferred from extension).')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format.')
@click.pass_context
def catalog_info(ctx, catalogs, fields, output, output_format):
    """Display metadata about one or more catalog databases.

    CATALOGS: One or more paths to .sqlite catalog files.

    Examples:
        ia-utils catalog-info spalteholz.sqlite
        ia-utils catalog-info *.sqlite --output-format table
        ia-utils catalog-info catalogs/*.sqlite -f ia_identifier -f title --output-format csv
    """
    if not catalogs:
        click.echo("Error: No catalog files specified.", err=True)
        sys.exit(1)

    # Collect info for all catalogs
    results: List[Dict[str, Any]] = []
    for catalog_path in catalogs:
        info = get_catalog_info(Path(catalog_path))
        results.append(info)

    # Determine fields to show
    if fields:
        field_list = list(fields)
        if '*' in field_list:
            # Show all fields from first result
            if results:
                output_fields = list(results[0].keys())
            else:
                output_fields = DEFAULT_FIELDS
        else:
            output_fields = field_list
    else:
        output_fields = list(DEFAULT_FIELDS)

    # Determine output format and path
    output_path = Path(output) if output else None
    format_name = determine_format(output_format, output_path)

    # For single catalog with no explicit format, use detailed records
    if len(results) == 1 and not output_format and not output:
        format_name = 'records'

    write_output(format_name, output_fields, results, output_path)
