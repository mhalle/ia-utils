"""Search Internet Archive catalog and display results."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple

import click

from ia_utils.core import ia_client
from ia_utils.utils.logger import Logger

DEFAULT_FIELDS = [
    'identifier',
    'url',
    'title',
    'creator',
    'date',
    'date_year',
    'mediatype',
    'primary_collection',
    'collection',
    'language',
    'rights',
    'subject',
    'format',
    'downloads',
    'ocr',
    'favorite_collections_count',
]
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

DATE_PATTERN = re.compile(r'(\d{4})')
FAVORITE_PREFIX = 'fav-'
COLLECTION_FIELDS = ('collection', 'collections_raw', 'collections_ordered', 'list_memberships', 'in')
FAVORITE_COUNT_FIELD = 'favorite_collections_count'


def _normalize_field_value(value: Any) -> str:
    """Convert IA field values (lists, dicts) into printable strings."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ', '.join(_normalize_field_value(v) for v in value if v)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_query(base_query: str, media_types: Iterable[str], collections: Iterable[str], languages: Iterable[str], formats: Iterable[str]) -> str:
    """Compose final IA query string including optional filters."""
    components = [f"({base_query.strip()})" if base_query.strip() else '*:*']

    def _quote(value: str) -> str:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    for media in media_types:
        if media:
            components.append(f"mediatype:{_quote(media)}")
    for coll in collections:
        if coll:
            components.append(f"collection:{_quote(coll)}")
    for lang in languages:
        if lang:
            components.append(f"language:{_quote(lang)}")
    for fmt in formats:
        if fmt:
            components.append(f"format:{_quote(fmt)}")
    return ' AND '.join(components)


def _parse_sorts(sorts: Iterable[str]) -> List[str]:
    parsed: List[str] = []
    for spec in sorts:
        if not spec:
            continue
        if ':' in spec:
            field, direction = spec.split(':', 1)
        elif ' ' in spec:
            field, direction = spec.split(None, 1)
        else:
            field, direction = spec, 'asc'
        direction = direction.strip().lower()
        if direction not in ('asc', 'desc'):
            direction = 'asc'
        parsed.append(f"{field.strip()} {direction}")
    return parsed


def _determine_format(explicit_format: str | None, output_path: Path | None) -> str:
    if explicit_format:
        return explicit_format
    if output_path:
        return FORMAT_EXTENSIONS.get(output_path.suffix.lower(), 'records')
    return 'records'


def _write_output(format_name: str,
                  fields: List[str],
                  results: List[Dict[str, Any]],
                  output_path: Path | None) -> None:
    """Write results to stdout or file in requested format."""
    rows = [[_normalize_field_value(item.get(field)) for field in fields] for item in results]

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
                value = _normalize_field_value(item.get(field))
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


def _expand_fields(fields: List[str], results: List[Dict[str, Any]]) -> List[str]:
    """Expand wildcard '*' into actual metadata keys preserving order."""
    if '*' not in fields:
        return fields

    expanded: List[str] = [field for field in fields if field != '*']
    seen = set(expanded)
    for item in results:
        for key in item.keys():
            if key not in seen:
                expanded.append(key)
                seen.add(key)
    return expanded


def _split_collection_string(value: str) -> Tuple[List[str], str | None]:
    if ';' in value:
        return [part.strip() for part in value.split(';') if part.strip()], ';'
    if ',' in value:
        return [part.strip() for part in value.split(',') if part.strip()], ','
    stripped = value.strip()
    return ([stripped] if stripped else [], None)


def _filter_favorite_entries(value: Any) -> Tuple[Any, int]:
    removed = 0

    if isinstance(value, list):
        filtered = []
        for entry in value:
            if _is_favorite_entry(str(entry)):
                removed += 1
            else:
                filtered.append(entry)
        return filtered, removed

    if isinstance(value, tuple):
        filtered_list = []
        for entry in value:
            if _is_favorite_entry(str(entry)):
                removed += 1
            else:
                filtered_list.append(entry)
        return tuple(filtered_list), removed

    if isinstance(value, str):
        parts, separator = _split_collection_string(value)
        filtered = []
        for part in parts:
            if _is_favorite_entry(part):
                removed += 1
            else:
                filtered.append(part)
        if not separator:
            return (filtered[0] if filtered else ''), removed
        joiner = ';' if separator == ';' else ', '
        return joiner.join(filtered), removed

    return value, removed


def _is_favorite_entry(entry: str) -> bool:
    return entry.lower().startswith(FAVORITE_PREFIX)


def _filter_collection_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    favorite_total = 0
    for field in COLLECTION_FIELDS:
        if field in item:
            filtered_value, removed = _filter_favorite_entries(item[field])
            item[field] = filtered_value
            favorite_total += removed

    if favorite_total or FAVORITE_COUNT_FIELD not in item:
        item[FAVORITE_COUNT_FIELD] = favorite_total

    ia_url = item.get('identifier-access') or item.get('identifier')
    if ia_url:
        if ia_url.startswith('http'):
            item['url'] = ia_url
        else:
            item['url'] = f"https://archive.org/details/{ia_url}"
    elif 'url' not in item:
        item['url'] = ''

    date_value = item.get('date') or item.get('date_raw')
    year = _extract_year(date_value) if isinstance(date_value, str) else None
    if year:
        item['date_year'] = year
    elif 'date_year' not in item:
        item['date_year'] = ''
    return item


def _extract_year(value: str) -> str | None:
    match = DATE_PATTERN.search(value)
    if match:
        return match.group(1)
    return None


def _build_stats_payload(query: str,
                         total: int,
                         page: int,
                         limit: int,
                         shown: int,
                         start_idx: int,
                         end_idx: int) -> tuple[List[str], List[Dict[str, Any]]]:
    fields = ['query', 'total', 'page', 'limit', 'shown', 'range_start', 'range_end']
    record = {
        'query': query,
        'total': total,
        'page': page,
        'limit': limit,
        'shown': shown,
        'range_start': start_idx,
        'range_end': end_idx,
    }
    return fields, [record]


@click.command(name='search-ia')
@click.option('-q', '--query', required=True, help='Internet Archive search query (Lucene syntax).')
@click.option('-m', '--media-type', 'media_types', multiple=True, help='Filter by media type (repeatable).')
@click.option('-c', '--collection', 'collections', multiple=True, help='Filter by collection (repeatable).')
@click.option('--lang', '--language', 'languages', multiple=True, help='Filter by language (repeatable).')
@click.option('-f', '--field', 'extra_fields', multiple=True, help='Fields to show (repeatable). Use "default" for defaults, "*" for all.')
@click.option('-s', '--sort', 'sorts', multiple=True, help='Sort results (field[:asc|desc]). Repeat for multiple sorts.')
@click.option('-p', '--page', type=int, default=1, show_default=True, help='Result page (1-indexed).')
@click.option('-l', '--limit', type=int, default=20, show_default=True, help='Number of results per page.')
@click.option('-F', '--format', 'formats', multiple=True, help='Filter by file format (repeatable).')
@click.option('-o', '--output', type=click.Path(dir_okay=False), help='Write results to file (format inferred from extension).')
@click.option('--output-format', 'output_format', type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']), help='Force output format.')
@click.option('--stats-only', is_flag=True, help='Emit only summary statistics in the requested output format.')
@click.pass_context
def search_ia(ctx, query, media_types, collections, languages, formats, extra_fields, sorts, page, limit, output, output_format, stats_only):
    """Search Internet Archive metadata and display matching items."""
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    extra_list = list(extra_fields)
    include_all = '*' in extra_list
    include_default = 'default' in extra_list
    filtered_extras = [f for f in extra_list if f not in ('*', 'default')]
    # If --field is specified, use only those fields (plus identifier); otherwise use defaults
    if extra_list:
        base_fields = (DEFAULT_FIELDS if include_default else ['identifier']) + filtered_extras
        combined_fields = list(dict.fromkeys(base_fields + (['*'] if include_all else [])))
    else:
        combined_fields = list(DEFAULT_FIELDS)
    final_query = _build_query(query, media_types, collections, languages, formats)
    parsed_sorts = _parse_sorts(sorts)
    output_path = Path(output) if output else None
    format_name = _determine_format(output_format, output_path)

    try:
        search_response = ia_client.search_items(
            final_query,
            fields=combined_fields,
            sorts=parsed_sorts or None,
            page=page,
            rows=limit,
            logger=logger,
            verbose=verbose
        )
    except Exception:
        raise click.Abort()

    total = search_response['total']
    results = [_filter_collection_fields(dict(item)) for item in search_response['results']]
    output_fields = _expand_fields(combined_fields, results)
    shown = len(results)
    start_idx = (page - 1) * limit + 1 if shown else 0
    end_idx = start_idx + shown - 1 if shown else 0

    if stats_only:
        stats_fields, stats_records = _build_stats_payload(
            final_query,
            total,
            page,
            limit,
            shown,
            start_idx,
            end_idx
        )
        _write_output(format_name, stats_fields, stats_records, output_path)
        return

    if format_name in ('records', 'table') and not results and not output_path:
        # Nothing else to print.
        return

    _write_output(format_name, output_fields, results, output_path)
