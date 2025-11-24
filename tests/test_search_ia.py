from pathlib import Path

from ia_utils.commands import search_ia


def test_build_query_with_filters():
    query = search_ia._build_query('title:atlas', ['texts'], ['smithsonian'])
    assert 'title:atlas' in query
    assert 'mediatype:"texts"' in query
    assert 'collection:"smithsonian"' in query


def test_parse_sorts_handles_various_forms():
    assert search_ia._parse_sorts(['date desc', 'downloads:asc', 'title']) == [
        'date desc',
        'downloads asc',
        'title asc',
    ]


def test_determine_format_prefers_explicit_format(tmp_path):
    output_path = tmp_path / 'results.json'
    output_path.touch()
    assert search_ia._determine_format('csv', output_path) == 'csv'
    assert search_ia._determine_format(None, output_path) == 'json'
    assert search_ia._determine_format(None, Path('results.unknown')) == 'records'


def test_write_output_records(tmp_path):
    output_path = tmp_path / 'results.txt'
    fields = ['identifier', 'title']
    rows = [
        {'identifier': 'foo', 'title': 'Foo Title'},
        {'identifier': 'bar', 'title': 'Second'},
    ]
    search_ia._write_output('records', fields, rows, output_path)
    text = output_path.read_text().strip()
    assert 'identifier: foo' in text
    assert 'title: Foo Title' in text
    assert '\n\nidentifier: bar' in text


def test_expand_fields_with_wildcard():
    fields = ['identifier', '*']
    rows = [
        {'identifier': 'foo', 'title': 'Foo', 'extra': 'value'},
        {'identifier': 'bar', 'creator': 'Someone', 'other': 'data'},
    ]
    expanded = search_ia._expand_fields(fields, rows)
    assert 'identifier' in expanded
    assert 'title' in expanded
    assert 'extra' in expanded
    assert 'other' in expanded


def test_filter_collection_fields_removes_favorites():
    item = {
        'collection': ['main', 'fav-demo', 'secondary'],
        'collections_ordered': 'main;fav-demo;secondary',
        'collections_raw': 'fav-one, keep-this',
        'list_memberships': ['fav-alpha', 'beta'],
        'in': ['texts', 'fav-gamma', 'image'],
    }
    filtered = search_ia._filter_collection_fields(dict(item))
    assert filtered['collection'] == ['main', 'secondary']
    assert filtered['collections_ordered'] == 'main;secondary'
    assert filtered['collections_raw'] == 'keep-this'
    assert filtered['list_memberships'] == ['beta']
    assert filtered['in'] == ['texts', 'image']
    assert filtered['favorite_collections_count'] == 5
    assert filtered['date_year'] == ''


def test_date_year_extraction():
    item = {
        'date': '1905-01-01T00:00:00Z',
        'collections_raw': 'main',
    }
    filtered = search_ia._filter_collection_fields(dict(item))
    assert filtered['date_year'] == '1905'
