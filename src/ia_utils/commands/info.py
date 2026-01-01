"""Display metadata about indexes or IA items."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

from ia_utils.core import ia_client
from ia_utils.core.database import get_document_metadata, get_index_metadata
from ia_utils.utils.output import determine_format, write_output
from ia_utils.utils.pages import extract_ia_id


# Default fields for index info (uses official IA field names)
INDEX_DEFAULT_FIELDS = [
    'filename',
    'identifier',
    'title',
    'creator',
    'date',
    'description',
    'mediatype',
    'collection',
    'subject',
    'language',
    'imagecount',
    'block_count',
    'ocr',
    'contributor',
    'licenseurl',
    'rights',
    'possible-copyright-status',
    'size_mb',
]

# Default fields for IA item info
IA_DEFAULT_FIELDS = [
    'identifier',
    'title',
    'creator',
    'date',
    'description',
    'mediatype',
    'collection',
    'language',
    'imagecount',
    'ocr',
    'licenseurl',
    'rights',
    'possible-copyright-status',
    'downloads',
]


def get_index_info(index_path: Path) -> Dict[str, Any]:
    """Extract metadata from an index database.

    Args:
        index_path: Path to the SQLite index file

    Returns:
        Dictionary with index metadata (all fields from DB plus computed fields)
    """
    try:
        db = sqlite_utils.Database(index_path)

        # Get document metadata (key-value table)
        doc_metadata = get_document_metadata(db)
        if not doc_metadata:
            return {'filename': index_path.name, 'error': 'No metadata found'}

        # Start with document metadata
        result = dict(doc_metadata)

        # Add index metadata
        idx_metadata = get_index_metadata(db)
        result.update(idx_metadata)

        # Add computed fields
        result['filename'] = index_path.name
        result['path'] = str(index_path)
        result['block_count'] = db['text_blocks'].count if 'text_blocks' in db.table_names() else 0
        result['size_mb'] = round(index_path.stat().st_size / 1024 / 1024, 2)

        return result
    except Exception as e:
        return {'filename': index_path.name, 'error': str(e)}


def get_ia_info(ia_id: str) -> Dict[str, Any]:
    """Fetch metadata from Internet Archive.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Dictionary with all IA metadata plus computed fields
    """
    try:
        meta = ia_client.get_metadata(ia_id)

        # Start with all raw metadata, joining list values
        result = {}
        for key, value in meta.items():
            if isinstance(value, list):
                result[key] = '; '.join(str(v) for v in value)
            else:
                result[key] = value

        # Add computed field
        result['url'] = f'https://archive.org/details/{ia_id}'

        return result
    except Exception as e:
        return {'identifier': ia_id, 'error': str(e)}


def is_index_file(path_str: str) -> bool:
    """Check if the argument is an index file."""
    if not path_str:
        return False
    path = Path(path_str)
    return path.suffix == '.sqlite' and path.exists()


@click.command('info')
@click.argument('identifier', required=False)
@click.option('-i', '--index', type=click.Path(exists=True),
              help='Index database path.')
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (repeatable). Use "*" for all fields.')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file (format inferred from extension).')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format.')
@click.pass_context
def info(ctx, identifier, index, fields, output, output_format):
    """Display metadata about an index or IA item.

    IDENTIFIER: IA identifier, URL, or path to .sqlite index.
    Auto-detects indexes by .sqlite extension.

    INDEX INFO (local .sqlite file):

    \b
    Default fields:
      filename, identifier, title, creator, date, description, mediatype,
      collection, subject, language, imagecount, block_count, ocr,
      contributor, licenseurl, rights, possible-copyright-status, size_mb
    All IA metadata fields are available with -f '*'

    IA ITEM INFO (remote identifier):

    \b
    Default fields:
      identifier, title, creator, date, description, mediatype, collection,
      language, imagecount, ocr, licenseurl, rights,
      possible-copyright-status, downloads
    All IA metadata fields are available with -f '*'

    EXAMPLES:

    \b
    # Index info
    ia-utils info book.sqlite
    ia-utils info -i book.sqlite
    # IA item info
    ia-utils info anatomicalatlasi00smit
    ia-utils info https://archive.org/details/anatomicalatlasi00smit
    # Specific fields
    ia-utils info book.sqlite -f title -f description
    # All fields as JSON
    ia-utils info anatomicalatlasi00smit -f '*' --output-format json
    """
    # Determine mode: index or IA identifier
    is_index = False
    target = None

    if index:
        # Explicit -i flag
        is_index = True
        target = index
        if identifier:
            click.echo("Error: Cannot specify both IDENTIFIER and -i/--index", err=True)
            sys.exit(1)
    elif identifier:
        # Check if it's an index file
        if is_index_file(identifier):
            is_index = True
            target = identifier
        else:
            # Treat as IA identifier
            is_index = False
            target = extract_ia_id(identifier)
    else:
        click.echo("Error: Provide an IDENTIFIER or use -i/--index", err=True)
        sys.exit(1)

    # Get info
    if is_index:
        result = get_index_info(Path(target))
        default_fields = INDEX_DEFAULT_FIELDS
    else:
        result = get_ia_info(target)
        default_fields = IA_DEFAULT_FIELDS

    # Check for errors
    if 'error' in result:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    results = [result]

    # Determine fields to show
    if fields:
        field_list = list(fields)
        if '*' in field_list:
            output_fields = list(result.keys())
        else:
            output_fields = field_list
    else:
        output_fields = list(default_fields)

    # Determine output format and path
    output_path = Path(output) if output else None
    format_name = determine_format(output_format, output_path)

    # Default to records for single item
    if not output_format and not output:
        format_name = 'records'

    write_output(format_name, output_fields, results, output_path)
