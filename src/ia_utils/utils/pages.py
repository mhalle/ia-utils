"""Page numbering and range parsing utilities."""

from typing import List, Optional, Tuple
import re
import sqlite_utils

from ia_utils.core import ia_client


def extract_ia_id(input_str: str) -> str:
    """Extract IA ID from URL or return as-is if already an ID."""
    if input_str.startswith('http'):
        # Parse URL: https://archive.org/details/IDENTIFIER
        if '/details/' in input_str:
            return input_str.split('/details/')[-1].split('/')[0]
    return input_str


def extract_ia_id_and_page(input_str: str) -> Tuple[str, Optional[int], Optional[str]]:
    """Extract IA ID and optional page number from URL or ID string.

    Handles formats like:
    - https://archive.org/details/b31362138/page/404/ (book page)
    - https://archive.org/details/b31362138/page/n404/ (sequential page, 0-origin)
    - https://archive.org/details/anatomicalatlasi00smit
    - anatomicalatlasi00smit

    Args:
        input_str: URL or IA identifier

    Returns:
        Tuple of (ia_id, page_number or None, page_type or None)
        page_type is 'page' for sequential (from /page/nXXX/) or 'book' for book pages
    """
    ia_id = extract_ia_id(input_str)  # Use existing function for IA ID extraction

    # Check for page info in URL
    page_num = None
    page_type = None
    if '/page/' in input_str:
        try:
            # Format: /page/404/ or /page/n404/
            page_part = input_str.split('/page/')[-1].rstrip('/')
            # Check if 'n' prefix is present (sequential page)
            if page_part.startswith('n'):
                page_type = 'page'
                page_part = page_part[1:]
            else:
                page_type = 'book'
            page_num = int(page_part)
        except (ValueError, IndexError):
            pass

    return ia_id, page_num, page_type


def normalize_page_number(page_input: str) -> int:
    """Convert page input (with or without leading zeros) to integer.

    Examples:
        '5' -> 5
        '0005' -> 5
        '001' -> 1
    """
    return int(page_input)


def get_page_number_for_jp2(page_num: int, page_type: str,
                            ia_id: Optional[str] = None,
                            db: Optional[sqlite_utils.Database] = None) -> int:
    """Convert from leaf/book page to sequential page number for jp2 files.

    JP2 files in the archive are numbered sequentially (1-indexed): _0001.jp2, _0002.jp2, etc.

    Args:
        page_num: The page number in the specified format
        page_type: 'page' (sequential), 'leaf' (physical page), or 'book' (book page number)
        ia_id: Internet Archive identifier (needed for book/leaf lookups)
        db: Optional sqlite_utils Database object (uses page_numbers table if available)

    Returns:
        The sequential page number (1-indexed) for the jp2 filename

    Raises:
        ValueError: If conversion fails
    """
    if page_type == 'page':
        # 'page' type is already the sequential page number
        return page_num

    elif page_type == 'leaf':
        # leaf number maps directly to sequential page number
        return page_num

    elif page_type == 'book':
        # 'book' page numbers need to be looked up in page_numbers table
        if db:
            try:
                result = db.execute(
                    "SELECT leaf_num FROM page_numbers WHERE book_page_number = ?",
                    [str(page_num)]
                ).fetchone()
                if result:
                    return result[0]
                else:
                    raise ValueError(f"Book page number {page_num} not found in page_numbers table")
            except Exception as e:
                raise ValueError(f"Could not look up book page number {page_num}: {e}")
        elif ia_id:
            # Download page_numbers.json on the fly
            try:
                page_data = ia_client.download_json(ia_id, f"{ia_id}_page_numbers.json")
                if page_data and 'pages' in page_data:
                    for page_entry in page_data['pages']:
                        if page_entry.get('pageNumber') == str(page_num):
                            return page_entry['leafNum']
                raise ValueError(f"Book page number {page_num} not found in page_numbers.json")
            except Exception as e:
                raise ValueError(f"Could not look up book page number {page_num}: {e}")
        else:
            raise ValueError("Book page lookup requires either catalog database or IA ID")

    else:
        raise ValueError(f"Unknown page_type: {page_type}")


def parse_page_range(range_str: str) -> List[int]:
    """Parse page range string into list of page numbers.

    Supports formats:
    - Single page: '42'
    - Range: '1-7' (inclusive)
    - Comma-separated: '1,3,5'
    - Mixed: '1-7,21,25,45-50'

    Args:
        range_str: Page range string

    Returns:
        Sorted list of unique integers

    Raises:
        ValueError: If format is invalid
    """
    pages = set()

    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue

        if '-' in part:
            # Range format: "1-7"
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                if start > end:
                    raise ValueError(f"Invalid range: {start}-{end} (start > end)")
                pages.update(range(start, end + 1))
            except ValueError as e:
                raise ValueError(f"Invalid range format '{part}': {e}")
        else:
            # Single page
            try:
                pages.add(int(part))
            except ValueError:
                raise ValueError(f"Invalid page number '{part}'")

    if not pages:
        raise ValueError("No valid page numbers parsed")

    return sorted(list(pages))
