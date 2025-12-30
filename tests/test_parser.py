"""Tests for parsing utilities."""

import pytest
from ia_utils.core.parser import (
    parse_bbox,
    parse_confidence,
    parse_font_size,
    parse_metadata,
    parse_files,
    parse_pageindex,
)


class TestParseBbox:
    def test_valid_bbox(self):
        title = 'bbox 100 200 300 400; x_wconf 95'
        result = parse_bbox(title)
        assert result == (100, 200, 300, 400)

    def test_bbox_only(self):
        title = 'bbox 0 0 1000 500'
        result = parse_bbox(title)
        assert result == (0, 0, 1000, 500)

    def test_no_bbox(self):
        title = 'x_wconf 95; x_fsize 12'
        result = parse_bbox(title)
        assert result == (None, None, None, None)

    def test_empty_string(self):
        result = parse_bbox('')
        assert result == (None, None, None, None)


class TestParseConfidence:
    def test_valid_confidence(self):
        title = 'bbox 0 0 100 50; x_wconf 95'
        result = parse_confidence(title)
        assert result == 95

    def test_low_confidence(self):
        title = 'x_wconf 42'
        result = parse_confidence(title)
        assert result == 42

    def test_no_confidence(self):
        title = 'bbox 0 0 100 50'
        result = parse_confidence(title)
        assert result is None

    def test_empty_string(self):
        result = parse_confidence('')
        assert result is None


class TestParseFontSize:
    def test_valid_font_size(self):
        title = 'bbox 0 0 100 50; x_fsize 24'
        result = parse_font_size(title)
        assert result == 24

    def test_no_font_size(self):
        title = 'bbox 0 0 100 50; x_wconf 95'
        result = parse_font_size(title)
        assert result is None

    def test_empty_string(self):
        result = parse_font_size('')
        assert result is None


class TestParseMetadata:
    def test_basic_metadata(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <metadata>
            <title>Test Book</title>
            <creator>John Doe</creator>
            <date>1920</date>
        </metadata>'''
        result = parse_metadata(xml)
        assert ('title', 'Test Book') in result
        assert ('creator', 'John Doe') in result
        assert ('date', '1920') in result

    def test_multiple_values_same_key(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <metadata>
            <subject>Medicine</subject>
            <subject>Anatomy</subject>
            <subject>Surgery</subject>
        </metadata>'''
        result = parse_metadata(xml)
        subjects = [v for k, v in result if k == 'subject']
        assert subjects == ['Medicine', 'Anatomy', 'Surgery']

    def test_empty_tags_ignored(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <metadata>
            <title>Book</title>
            <empty></empty>
        </metadata>'''
        result = parse_metadata(xml)
        keys = [k for k, v in result]
        assert 'empty' not in keys


class TestParseFiles:
    def test_basic_files(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <files>
            <file name="test.pdf" source="derivative">
                <format>PDF</format>
                <size>1024</size>
                <md5>abc123</md5>
            </file>
        </files>'''
        result = parse_files(xml)
        assert len(result) == 1
        assert result[0]['filename'] == 'test.pdf'
        assert result[0]['format'] == 'PDF'
        assert result[0]['size'] == 1024
        assert result[0]['source'] == 'derivative'
        assert result[0]['md5'] == 'abc123'

    def test_multiple_files(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <files>
            <file name="a.pdf"><format>PDF</format><size>100</size></file>
            <file name="b.epub"><format>EPUB</format><size>200</size></file>
            <file name="c.txt"><format>Text</format><size>50</size></file>
        </files>'''
        result = parse_files(xml)
        assert len(result) == 3
        filenames = [f['filename'] for f in result]
        assert filenames == ['a.pdf', 'b.epub', 'c.txt']

    def test_missing_fields_default_values(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <files>
            <file name="test.pdf"></file>
        </files>'''
        result = parse_files(xml)
        assert result[0]['format'] == ''
        assert result[0]['size'] == 0
        assert result[0]['source'] == ''


class TestParsePageindex:
    def test_basic_pageindex(self):
        data = b'[[0, 100, 0, 500], [100, 200, 500, 1000], [200, 300, 1000, 1500]]'
        result = parse_pageindex(data)
        assert len(result) == 3
        assert result[0] == (0, 100, 0, 500)
        assert result[1] == (100, 200, 500, 1000)
        assert result[2] == (200, 300, 1000, 1500)

    def test_empty_pageindex(self):
        data = b'[]'
        result = parse_pageindex(data)
        assert result == []
