"""Tests for page parsing utilities."""

import pytest
from ia_utils.utils.pages import (
    extract_ia_id,
    extract_ia_id_and_page,
    normalize_page_number,
    parse_page_range,
)


class TestExtractIaId:
    def test_returns_id_as_is(self):
        assert extract_ia_id('b31362138') == 'b31362138'

    def test_extracts_from_details_url(self):
        url = 'https://archive.org/details/anatomicalatlasi00smit'
        assert extract_ia_id(url) == 'anatomicalatlasi00smit'

    def test_extracts_from_url_with_page(self):
        url = 'https://archive.org/details/b31362138/page/leaf5/'
        assert extract_ia_id(url) == 'b31362138'

    def test_extracts_from_url_with_trailing_slash(self):
        url = 'https://archive.org/details/b31362138/'
        assert extract_ia_id(url) == 'b31362138'

    def test_handles_http_url(self):
        url = 'http://archive.org/details/b31362138'
        assert extract_ia_id(url) == 'b31362138'


class TestExtractIaIdAndPage:
    def test_simple_id_no_page(self):
        ia_id, page_num, page_type = extract_ia_id_and_page('b31362138')
        assert ia_id == 'b31362138'
        assert page_num is None
        assert page_type is None

    def test_url_no_page(self):
        url = 'https://archive.org/details/anatomicalatlasi00smit'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'anatomicalatlasi00smit'
        assert page_num is None
        assert page_type is None

    def test_url_with_leaf_page(self):
        url = 'https://archive.org/details/b31362138/page/leaf5/'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'b31362138'
        assert page_num == 5
        assert page_type == 'leaf'

    def test_url_with_n_prefix_page(self):
        # n prefix should be treated as leaf for compatibility
        url = 'https://archive.org/details/b31362138/page/n10/'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'b31362138'
        assert page_num == 10
        assert page_type == 'leaf'

    def test_url_with_book_page(self):
        url = 'https://archive.org/details/b31362138/page/42/'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'b31362138'
        assert page_num == 42
        assert page_type == 'book'

    def test_url_with_page_no_trailing_slash(self):
        url = 'https://archive.org/details/b31362138/page/leaf15'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'b31362138'
        assert page_num == 15
        assert page_type == 'leaf'

    def test_invalid_page_number_ignored(self):
        # When page number can't be parsed, page_num is None but page_type
        # may still be set based on prefix detection
        url = 'https://archive.org/details/b31362138/page/invalid/'
        ia_id, page_num, page_type = extract_ia_id_and_page(url)
        assert ia_id == 'b31362138'
        assert page_num is None
        # page_type gets set to 'book' before int conversion fails
        assert page_type == 'book'


class TestNormalizePageNumber:
    def test_simple_number(self):
        assert normalize_page_number('5') == 5

    def test_leading_zeros(self):
        assert normalize_page_number('0005') == 5

    def test_single_digit_with_zeros(self):
        assert normalize_page_number('001') == 1

    def test_large_number(self):
        assert normalize_page_number('1234') == 1234


class TestParsePageRange:
    def test_single_page(self):
        assert parse_page_range('42') == [42]

    def test_simple_range(self):
        assert parse_page_range('1-5') == [1, 2, 3, 4, 5]

    def test_comma_separated(self):
        assert parse_page_range('1,3,5') == [1, 3, 5]

    def test_mixed_format(self):
        assert parse_page_range('1-3,7,10-12') == [1, 2, 3, 7, 10, 11, 12]

    def test_whitespace_handling(self):
        assert parse_page_range(' 1 - 3 , 5 ') == [1, 2, 3, 5]

    def test_removes_duplicates(self):
        assert parse_page_range('1-3,2-4') == [1, 2, 3, 4]

    def test_returns_sorted(self):
        assert parse_page_range('10,1,5') == [1, 5, 10]

    def test_invalid_range_start_greater_than_end(self):
        with pytest.raises(ValueError, match='start > end'):
            parse_page_range('5-1')

    def test_invalid_page_number(self):
        with pytest.raises(ValueError, match='Invalid page number'):
            parse_page_range('abc')

    def test_empty_input(self):
        with pytest.raises(ValueError, match='No valid page numbers'):
            parse_page_range('')

    def test_only_commas(self):
        with pytest.raises(ValueError, match='No valid page numbers'):
            parse_page_range(',,,')
