"""List files in an Internet Archive item."""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import sqlite_utils

from ia_utils.core import ia_client
from ia_utils.core.database import get_document_metadata
from ia_utils.utils.output import determine_format, write_output
from ia_utils.utils.pages import extract_ia_id


# Default fields to display
DEFAULT_FIELDS = ['name', 'format', 'size', 'url']

# All available fields from IA file metadata
ALL_FIELDS = ['name', 'source', 'format', 'size', 'md5', 'mtime', 'crc32', 'sha1', 'url']


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes is None:
        return ''
    size = int(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_file_list(ia_id: str, include_all: bool = False) -> List[Dict[str, Any]]:
    """Get list of files from an IA item with download URLs.

    Args:
        ia_id: Internet Archive identifier
        include_all: Include derivative/metadata files

    Returns:
        List of file info dicts with download URLs
    """
    files = ia_client.get_files(ia_id)
    result = []

    for f in files:
        # Skip derivative files unless requested
        source = f.get('source', '')
        if not include_all and source == 'derivative':
            continue

        file_info = {
            'name': f.get('name', ''),
            'source': source,
            'format': f.get('format', ''),
            'size': f.get('size', ''),
            'size_formatted': format_size(f.get('size')),
            'md5': f.get('md5', ''),
            'mtime': f.get('mtime', ''),
            'crc32': f.get('crc32', ''),
            'sha1': f.get('sha1', ''),
            'url': f"https://archive.org/download/{ia_id}/{f.get('name', '')}",
        }
        result.append(file_info)

    return result


@click.command('list-files')
@click.argument('identifier', required=False)
@click.option('-i', '--index', type=click.Path(exists=True),
              help='Index database path.')
@click.option('-f', '--field', 'fields', multiple=True,
              help='Fields to show (repeatable). Use "*" for all fields.')
@click.option('--all', 'include_all', is_flag=True,
              help='Include derivative files (thumbnails, OCR, etc.)')
@click.option('--format-filter', 'format_filter',
              help='Filter by format (e.g., "PDF", "JPEG", "DjVu")')
@click.option('-o', '--output', type=click.Path(dir_okay=False),
              help='Write results to file (format inferred from extension).')
@click.option('--output-format', 'output_format',
              type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']),
              help='Output format.')
@click.pass_context
def list_files(ctx, identifier, index, fields, include_all, format_filter, output, output_format):
    """List files in an Internet Archive item.

    Shows all original files with download URLs. Use --all to include
    derivative files (thumbnails, OCR text, etc.).

    IDENTIFIER: IA identifier or URL (optional if -i provided).

    DEFAULT FIELDS: name, format, size, url

    ALL FIELDS: name, source, format, size, md5, mtime, crc32, sha1, url

    Examples:
        ia-utils list-files anatomicalatlasi00smit
        ia-utils list-files -i index.sqlite
        ia-utils list-files anatomicalatlasi00smit --all
        ia-utils list-files anatomicalatlasi00smit --format-filter PDF
        ia-utils list-files anatomicalatlasi00smit -f '*' --output-format json
        ia-utils list-files anatomicalatlasi00smit -o files.csv
    """
    # Get IA identifier
    ia_id = None

    if index:
        try:
            db = sqlite_utils.Database(index)
            doc_metadata = get_document_metadata(db)
            if not doc_metadata:
                click.echo("Error: No metadata found in index database", err=True)
                sys.exit(1)
            ia_id = doc_metadata.get('identifier')
        except Exception as e:
            click.echo(f"Error reading index: {e}", err=True)
            sys.exit(1)

    if identifier:
        id_from_arg = extract_ia_id(identifier)
        if ia_id and ia_id != id_from_arg:
            click.echo(f"Error: ID mismatch - argument: {id_from_arg}, index: {ia_id}", err=True)
            sys.exit(1)
        ia_id = id_from_arg

    if not ia_id:
        click.echo("Error: Provide an IDENTIFIER or use -i/--index", err=True)
        sys.exit(1)

    # Get file list
    try:
        results = get_file_list(ia_id, include_all=include_all)
    except Exception as e:
        click.echo(f"Error fetching files: {e}", err=True)
        sys.exit(1)

    if not results:
        click.echo("No files found", err=True)
        sys.exit(0)

    # Apply format filter
    if format_filter:
        filter_lower = format_filter.lower()
        results = [f for f in results if filter_lower in f.get('format', '').lower()]

    # Determine fields to show
    if fields:
        field_list = list(fields)
        if '*' in field_list:
            output_fields = ALL_FIELDS
        else:
            output_fields = field_list
    else:
        output_fields = DEFAULT_FIELDS

    # Determine output format
    output_path = Path(output) if output else None
    format_name = determine_format(output_format, output_path)

    # Default to table for multiple items
    if not output_format and not output:
        format_name = 'table'

    write_output(format_name, output_fields, results, output_path)
