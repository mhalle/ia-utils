"""Output formatting utilities for CLI commands."""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any

import click


FORMAT_EXTENSIONS = {
    '.json': 'json',
    '.jsonl': 'jsonl',
    '.ndjson': 'jsonl',
    '.csv': 'csv',
    '.yaml': 'records',
    '.yml': 'records',
    '.md': 'records',
    '.txt': 'records',
}


def normalize_field_value(value: Any) -> str:
    """Convert field values (lists, dicts) into printable strings."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        # Only filter out None values, preserve falsy values like 0, False, ''
        return ', '.join(normalize_field_value(v) for v in value if v is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def determine_format(explicit_format: str | None, output_path: Path | None) -> str:
    """Determine output format from explicit option or file extension."""
    if explicit_format:
        return explicit_format
    if output_path:
        return FORMAT_EXTENSIONS.get(output_path.suffix.lower(), 'records')
    return 'records'


def write_output(format_name: str,
                 fields: List[str],
                 results: List[Dict[str, Any]],
                 output_path: Path | None = None) -> None:
    """Write results to stdout or file in requested format.

    Args:
        format_name: One of 'json', 'jsonl', 'csv', 'records', 'table'
        fields: List of field names to include
        results: List of dictionaries containing the data
        output_path: Optional path to write to (otherwise stdout)
    """
    rows = [[normalize_field_value(item.get(field)) for field in fields] for item in results]

    if format_name == 'json':
        payload = [
            {field: item.get(field) for field in fields}
            for item in results
        ]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if output_path:
            output_path.write_text(text, encoding='utf-8')
        else:
            click.echo(text)
        return

    if format_name == 'jsonl':
        lines = [
            json.dumps({field: item.get(field) for field in fields}, ensure_ascii=False)
            for item in results
        ]
        text = '\n'.join(lines)
        if output_path:
            output_path.write_text(text + ('\n' if lines else ''), encoding='utf-8')
        else:
            click.echo(text)
        return

    if format_name == 'csv':
        if output_path:
            handle = output_path.open('w', newline='', encoding='utf-8')
            close_handle = True
        else:
            handle = click.get_text_stream('stdout')
            close_handle = False
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)
        if close_handle:
            handle.close()
        return

    if format_name == 'records':
        lines: List[str] = []
        for idx, item in enumerate(results):
            for field in fields:
                value = normalize_field_value(item.get(field))
                lines.append(f"{field}: {value}".rstrip())
            if idx != len(results) - 1:
                lines.append('')
        text = '\n'.join(lines)
        if output_path:
            output_path.write_text((text + '\n') if text else '', encoding='utf-8')
        else:
            click.echo(text)
        return

    # table output
    widths = [len(field) for field in fields]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _format_row(cells: List[str]) -> str:
        return '  '.join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    header = _format_row(fields)
    divider = '  '.join('-' * width for width in widths)
    lines = [header, divider]
    lines.extend(_format_row(row) for row in rows)
    output = '\n'.join(lines)
    if output_path:
        output_path.write_text(output + ('\n' if output else ''), encoding='utf-8')
    else:
        click.echo(output)
