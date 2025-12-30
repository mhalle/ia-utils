"""Tests for output formatting utilities."""

import json
from pathlib import Path

import pytest
from ia_utils.utils.output import (
    normalize_field_value,
    determine_format,
    write_output,
)


class TestNormalizeFieldValue:
    def test_string_passthrough(self):
        assert normalize_field_value('hello') == 'hello'

    def test_integer_to_string(self):
        assert normalize_field_value(42) == '42'

    def test_none_to_empty(self):
        assert normalize_field_value(None) == ''

    def test_list_to_comma_separated(self):
        assert normalize_field_value(['a', 'b', 'c']) == 'a, b, c'

    def test_tuple_to_comma_separated(self):
        assert normalize_field_value(('x', 'y')) == 'x, y'

    def test_nested_list(self):
        result = normalize_field_value([['a', 'b'], 'c'])
        assert result == 'a, b, c'

    def test_dict_to_json(self):
        result = normalize_field_value({'key': 'value'})
        assert result == '{"key": "value"}'

    def test_empty_list(self):
        assert normalize_field_value([]) == ''

    def test_list_with_none_values(self):
        assert normalize_field_value(['a', None, 'b']) == 'a, b'

    def test_float_to_string(self):
        assert normalize_field_value(3.14) == '3.14'


class TestDetermineFormat:
    def test_explicit_format_overrides(self):
        assert determine_format('csv', Path('results.json')) == 'csv'
        assert determine_format('json', Path('results.txt')) == 'json'

    def test_json_extension(self):
        assert determine_format(None, Path('results.json')) == 'json'

    def test_jsonl_extension(self):
        assert determine_format(None, Path('results.jsonl')) == 'jsonl'

    def test_ndjson_extension(self):
        assert determine_format(None, Path('results.ndjson')) == 'jsonl'

    def test_csv_extension(self):
        assert determine_format(None, Path('results.csv')) == 'csv'

    def test_txt_extension(self):
        assert determine_format(None, Path('results.txt')) == 'records'

    def test_md_extension(self):
        assert determine_format(None, Path('results.md')) == 'records'

    def test_unknown_extension(self):
        assert determine_format(None, Path('results.xyz')) == 'records'

    def test_no_output_path(self):
        assert determine_format(None, None) == 'records'

    def test_case_insensitive_extension(self):
        assert determine_format(None, Path('results.JSON')) == 'json'
        assert determine_format(None, Path('results.CSV')) == 'csv'


class TestWriteOutput:
    def test_records_format(self, tmp_path):
        output_path = tmp_path / 'results.txt'
        fields = ['id', 'name']
        rows = [
            {'id': '1', 'name': 'First'},
            {'id': '2', 'name': 'Second'},
        ]
        write_output('records', fields, rows, output_path)
        text = output_path.read_text()
        assert 'id: 1' in text
        assert 'name: First' in text
        assert 'id: 2' in text
        assert 'name: Second' in text

    def test_json_format(self, tmp_path):
        output_path = tmp_path / 'results.json'
        fields = ['id', 'title']
        rows = [{'id': 'a', 'title': 'Test', 'extra': 'ignored'}]
        write_output('json', fields, rows, output_path)
        data = json.loads(output_path.read_text())
        assert len(data) == 1
        assert data[0]['id'] == 'a'
        assert data[0]['title'] == 'Test'
        assert 'extra' not in data[0]

    def test_jsonl_format(self, tmp_path):
        output_path = tmp_path / 'results.jsonl'
        fields = ['id']
        rows = [{'id': '1'}, {'id': '2'}, {'id': '3'}]
        write_output('jsonl', fields, rows, output_path)
        lines = output_path.read_text().strip().split('\n')
        assert len(lines) == 3
        assert json.loads(lines[0]) == {'id': '1'}
        assert json.loads(lines[1]) == {'id': '2'}
        assert json.loads(lines[2]) == {'id': '3'}

    def test_csv_format(self, tmp_path):
        output_path = tmp_path / 'results.csv'
        fields = ['id', 'name']
        rows = [
            {'id': '1', 'name': 'Alice'},
            {'id': '2', 'name': 'Bob'},
        ]
        write_output('csv', fields, rows, output_path)
        text = output_path.read_text()
        lines = text.strip().split('\n')
        assert lines[0] == 'id,name'
        assert lines[1] == '1,Alice'
        assert lines[2] == '2,Bob'

    def test_csv_with_commas_in_values(self, tmp_path):
        output_path = tmp_path / 'results.csv'
        fields = ['name']
        rows = [{'name': 'Smith, John'}]
        write_output('csv', fields, rows, output_path)
        text = output_path.read_text()
        # CSV should quote values containing commas
        assert '"Smith, John"' in text

    def test_table_format(self, tmp_path):
        output_path = tmp_path / 'results.txt'
        fields = ['id', 'name']
        rows = [
            {'id': '1', 'name': 'Short'},
            {'id': '2', 'name': 'LongerName'},
        ]
        write_output('table', fields, rows, output_path)
        text = output_path.read_text()
        lines = text.strip().split('\n')
        # Should have header, divider, and data rows
        assert len(lines) == 4
        assert 'id' in lines[0]
        assert 'name' in lines[0]
        assert '--' in lines[1]

    def test_empty_results(self, tmp_path):
        output_path = tmp_path / 'results.json'
        write_output('json', ['id'], [], output_path)
        data = json.loads(output_path.read_text())
        assert data == []

    def test_missing_field_in_row(self, tmp_path):
        output_path = tmp_path / 'results.json'
        fields = ['id', 'missing']
        rows = [{'id': '1'}]
        write_output('json', fields, rows, output_path)
        data = json.loads(output_path.read_text())
        assert data[0]['id'] == '1'
        assert data[0]['missing'] is None
