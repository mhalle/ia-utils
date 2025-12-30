"""Tests for search-ia command utilities."""

from pathlib import Path

import pytest
from ia_utils.commands import search_ia
from ia_utils.utils import output


class TestParseYear:
    def test_exact_year(self):
        result = search_ia._parse_year('1900')
        assert result == 'date:[1900-01-01 TO 1900-12-31]'

    def test_year_range(self):
        result = search_ia._parse_year('1900-1950')
        assert result == 'date:[1900-01-01 TO 1950-12-31]'

    def test_year_range_open_end(self):
        result = search_ia._parse_year('1900-')
        assert result == 'date:[1900-01-01 TO *]'

    def test_year_range_open_start(self):
        result = search_ia._parse_year('-1950')
        assert result == 'date:[* TO 1950-12-31]'

    def test_whitespace_handling(self):
        result = search_ia._parse_year('  1900  ')
        assert result == 'date:[1900-01-01 TO 1900-12-31]'

    def test_invalid_year(self):
        assert search_ia._parse_year('abc') is None

    def test_empty_string(self):
        assert search_ia._parse_year('') is None


class TestBuildQuery:
    def test_basic_query_with_filters(self):
        query = search_ia._build_query('title:atlas', ['texts'], ['smithsonian'], [], [])
        assert 'title:atlas' in query
        assert 'mediatype:"texts"' in query
        assert 'collection:"smithsonian"' in query

    def test_multiple_media_types(self):
        query = search_ia._build_query('test', ['texts', 'audio'], [], [], [])
        assert 'mediatype:"texts"' in query
        assert 'mediatype:"audio"' in query

    def test_multiple_collections(self):
        query = search_ia._build_query('test', [], ['wellcome', 'medical'], [], [])
        assert 'collection:"wellcome"' in query
        assert 'collection:"medical"' in query

    def test_language_filter(self):
        query = search_ia._build_query('test', [], [], ['eng', 'ger'], [])
        assert 'language:"eng"' in query
        assert 'language:"ger"' in query

    def test_format_filter(self):
        query = search_ia._build_query('test', [], [], [], ['PDF', 'DjVu'])
        assert 'format:"PDF"' in query
        assert 'format:"DjVu"' in query

    def test_creator_filter(self):
        query = search_ia._build_query('test', [], [], [], [], creators=['Smith'])
        assert 'creator:"Smith"' in query

    def test_subject_filter(self):
        query = search_ia._build_query('test', [], [], [], [], subjects=['anatomy'])
        assert 'subject:"anatomy"' in query

    def test_source_filter(self):
        query = search_ia._build_query('test', [], [], [], [], sources=['wellcome'])
        assert 'source:"wellcome"' in query

    def test_year_filter(self):
        query = search_ia._build_query('test', [], [], [], [], year='1900')
        assert 'date:[1900-01-01 TO 1900-12-31]' in query

    def test_has_ocr_filter(self):
        query = search_ia._build_query('test', [], [], [], [], has_ocr=True)
        assert 'ocr:*' in query

    def test_text_terms(self):
        query = search_ia._build_query('', [], [], [], [], text_terms=['anatomy', 'heart'])
        assert 'text:(anatomy)' in query
        assert 'text:(heart)' in query

    def test_empty_query_matches_all(self):
        query = search_ia._build_query('', [], [], [], [])
        assert '*:*' in query

    def test_available_only_default(self):
        query = search_ia._build_query('test', [], [], [], [])
        assert 'NOT collection:printdisabled' in query
        assert 'NOT indexflag:removed' in query

    def test_include_unavailable(self):
        query = search_ia._build_query('test', [], [], [], [], available_only=False)
        assert 'NOT collection:printdisabled' not in query
        assert 'NOT indexflag:removed' not in query

    def test_quotes_in_values_escaped(self):
        query = search_ia._build_query('test', [], ['collection"name'], [], [])
        assert 'collection:"collection\\"name"' in query


class TestParseSorts:
    def test_space_separated(self):
        assert search_ia._parse_sorts(['date desc']) == ['date desc']

    def test_colon_separated(self):
        assert search_ia._parse_sorts(['downloads:asc']) == ['downloads asc']

    def test_default_direction(self):
        assert search_ia._parse_sorts(['title']) == ['title asc']

    def test_multiple_sorts(self):
        result = search_ia._parse_sorts(['date desc', 'downloads:asc', 'title'])
        assert result == ['date desc', 'downloads asc', 'title asc']

    def test_invalid_direction_defaults_to_asc(self):
        assert search_ia._parse_sorts(['date:invalid']) == ['date asc']

    def test_empty_sorts(self):
        assert search_ia._parse_sorts([]) == []

    def test_empty_string_ignored(self):
        assert search_ia._parse_sorts(['', 'date desc', '']) == ['date desc']


class TestExpandFields:
    def test_no_wildcard(self):
        fields = ['identifier', 'title']
        rows = [{'identifier': 'a', 'title': 'b', 'extra': 'c'}]
        result = search_ia._expand_fields(fields, rows)
        assert result == ['identifier', 'title']

    def test_wildcard_expands(self):
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

    def test_preserves_order(self):
        fields = ['a', 'b', '*']
        rows = [{'a': '1', 'b': '2', 'c': '3', 'd': '4'}]
        result = search_ia._expand_fields(fields, rows)
        assert result[:2] == ['a', 'b']

    def test_empty_rows(self):
        fields = ['identifier', '*']
        rows = []
        result = search_ia._expand_fields(fields, rows)
        assert result == ['identifier']


class TestFilterCollectionFields:
    def test_removes_favorites_from_list(self):
        item = {
            'collection': ['main', 'fav-demo', 'secondary'],
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['collection'] == ['main', 'secondary']

    def test_removes_favorites_from_semicolon_string(self):
        item = {
            'collections_ordered': 'main;fav-demo;secondary',
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['collections_ordered'] == 'main;secondary'

    def test_removes_favorites_from_comma_string(self):
        item = {
            'collections_raw': 'fav-one, keep-this',
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['collections_raw'] == 'keep-this'

    def test_counts_removed_favorites(self):
        item = {
            'collection': ['main', 'fav-demo', 'secondary'],
            'collections_ordered': 'main;fav-demo;secondary',
            'collections_raw': 'fav-one, keep-this',
            'list_memberships': ['fav-alpha', 'beta'],
            'in': ['texts', 'fav-gamma', 'image'],
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['favorite_collections_count'] == 5

    def test_extracts_date_year(self):
        item = {
            'date': '1905-01-01T00:00:00Z',
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['date_year'] == '1905'

    def test_extracts_year_from_simple_date(self):
        item = {'date': '1920'}
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['date_year'] == '1920'

    def test_adds_url_from_identifier(self):
        item = {'identifier': 'test123'}
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['url'] == 'https://archive.org/details/test123'

    def test_uses_identifier_access_as_url(self):
        item = {
            'identifier': 'test123',
            'identifier-access': 'http://archive.org/details/test123',
        }
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['url'] == 'http://archive.org/details/test123'

    def test_empty_date_year_when_no_date(self):
        item = {}
        filtered = search_ia._filter_collection_fields(dict(item))
        assert filtered['date_year'] == ''
