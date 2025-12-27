"""Search Internet Archive catalog and display results."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple

import click

from ia_utils.core import ia_client
from ia_utils.utils.logger import Logger
from ia_utils.utils.output import determine_format, write_output, normalize_field_value

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

DATE_PATTERN = re.compile(r'(\d{4})')
YEAR_RANGE_PATTERN = re.compile(r'^(\d{4})?-(\d{4})?$')
FAVORITE_PREFIX = 'fav-'
COLLECTION_FIELDS = ('collection', 'collections_raw', 'collections_ordered', 'list_memberships', 'in')
FAVORITE_COUNT_FIELD = 'favorite_collections_count'


def _parse_year(year_spec: str) -> str | None:
    """Parse year specification into IA date range query.

    Formats:
        1900        -> date:[1900-01-01 TO 1900-12-31]
        1900-1950   -> date:[1900-01-01 TO 1950-12-31]
        1900-       -> date:[1900-01-01 TO *]
        -1950       -> date:[* TO 1950-12-31]

    Returns:
        IA query string fragment, or None if invalid
    """
    year_spec = year_spec.strip()
    if not year_spec:
        return None

    # Exact year: 1900
    if re.match(r'^\d{4}$', year_spec):
        return f"date:[{year_spec}-01-01 TO {year_spec}-12-31]"

    # Range: 1900-1950, 1900-, -1950
    match = YEAR_RANGE_PATTERN.match(year_spec)
    if match:
        start_year, end_year = match.groups()
        start = f"{start_year}-01-01" if start_year else "*"
        end = f"{end_year}-12-31" if end_year else "*"
        return f"date:[{start} TO {end}]"

    return None


def _build_query(base_query: str,
                 media_types: Iterable[str],
                 collections: Iterable[str],
                 languages: Iterable[str],
                 formats: Iterable[str],
                 creators: Iterable[str] = (),
                 subjects: Iterable[str] = (),
                 sources: Iterable[str] = (),
                 year: str | None = None,
                 has_ocr: bool = False) -> str:
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
    for creator in creators:
        if creator:
            components.append(f"creator:{_quote(creator)}")
    for subject in subjects:
        if subject:
            components.append(f"subject:{_quote(subject)}")
    for source in sources:
        if source:
            components.append(f"source:{_quote(source)}")
    if year:
        year_query = _parse_year(year)
        if year_query:
            components.append(year_query)
    if has_ocr:
        components.append("ocr:*")
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
@click.option('-q', '--query', default='', help='Search query (Lucene syntax). If omitted, matches all items.')
@click.option('-m', '--media-type', 'media_types', multiple=True, help='Filter by media type (repeatable).')
@click.option('-c', '--collection', 'collections', multiple=True, help='Filter by collection (repeatable).')
@click.option('--lang', '--language', 'languages', multiple=True, help='Filter by language (repeatable).')
@click.option('--year', help='Year or range: 1900, 1900-1950, 1900-, -1950')
@click.option('--creator', 'creators', multiple=True, help='Filter by creator/author (repeatable).')
@click.option('--subject', 'subjects', multiple=True, help='Filter by subject (repeatable).')
@click.option('--source', 'sources', multiple=True, help='Filter by source/contributor (repeatable).')
@click.option('--has-ocr', is_flag=True, help='Only items with OCR text.')
@click.option('-f', '--field', 'extra_fields', multiple=True, help='Fields to show (repeatable). Use "default" for defaults, "*" for all.')
@click.option('-s', '--sort', 'sorts', multiple=True, help='Sort results (field[:asc|desc]). Repeat for multiple sorts.')
@click.option('-p', '--page', type=int, default=1, show_default=True, help='Result page (1-indexed).')
@click.option('-l', '--limit', type=int, default=20, show_default=True, help='Number of results per page.')
@click.option('-F', '--format', 'formats', multiple=True, help='Filter by file format (repeatable).')
@click.option('-o', '--output', type=click.Path(dir_okay=False), help='Write results to file (format inferred from extension).')
@click.option('--output-format', 'output_format', type=click.Choice(['records', 'table', 'json', 'jsonl', 'csv']), help='Force output format.')
@click.option('--stats-only', is_flag=True, help='Emit only summary statistics in the requested output format.')
@click.pass_context
def search_ia(ctx, query, media_types, collections, languages, year, creators, subjects, sources, has_ocr, extra_fields, sorts, page, limit, formats, output, output_format, stats_only):
    """Search Internet Archive metadata and display matching items.

    QUERY (-q):
    Uses Lucene syntax. If omitted, matches all items (use filters to narrow).
    Examples: "anatomy atlas", "title:spalteholz", "description:illustrated"

    FILTERS:
    All filters are combined with AND. Repeatable filters allow multiple values.

    \b
      --year         Year or range: 1900, 1900-1950, 1900- (after), -1950 (before)
      --creator      Author/creator name
      --subject      Subject/topic
      --source       Contributing library or source
      --collection   IA collection (e.g., medicallibrary, wellcomelibrary)
      --media-type   texts, audio, movies, image, software, etc.
      --language     eng, ger, fre, etc.
      --format       DjVu, PDF, EPUB, etc.
      --has-ocr      Only items with OCR/searchable text

    OUTPUT FORMATS (--output-format):

    \b
    records   Key-value pairs (default for single results)
    table     Aligned columns (default for multiple results)
    json      JSON array
    jsonl     JSON Lines (one object per line)
    csv       Comma-separated values

    FIELD SELECTION (-f/--field):

    \b
    -f title -f date       Show only these fields
    -f default -f source   Add source to default fields
    -f '*'                 Show all available fields

    EXAMPLES:

    \b
    # Find anatomy atlases from 1900-1940
    ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts
    # Browse a collection with OCR
    ia-utils search-ia -c wellcomelibrary --has-ocr -m texts -l 50
    # Find books by author
    ia-utils search-ia --creator "Spalteholz" --year 1900-1950
    # Export to CSV
    ia-utils search-ia -q "apple cultivation" -o results.csv
    # Get just identifiers for scripting
    ia-utils search-ia --subject "botany" -f identifier --output-format jsonl
    """
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
    final_query = _build_query(
        query, media_types, collections, languages, formats,
        creators=creators, subjects=subjects, sources=sources,
        year=year, has_ocr=has_ocr
    )
    parsed_sorts = _parse_sorts(sorts)
    output_path = Path(output) if output else None
    format_name = determine_format(output_format, output_path)

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
        write_output(format_name, stats_fields, stats_records, output_path)
        return

    if format_name in ('records', 'table') and not results and not output_path:
        # Nothing else to print.
        return

    write_output(format_name, output_fields, results, output_path)
