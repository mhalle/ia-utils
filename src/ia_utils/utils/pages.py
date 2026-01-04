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
    - https://archive.org/details/b31362138/page/leaf5/ (leaf number)
    - https://archive.org/details/b31362138/page/n5/ (treated as leaf for compatibility)
    - https://archive.org/details/b31362138/page/42/ (book page number)
    - https://archive.org/details/anatomicalatlasi00smit
    - anatomicalatlasi00smit

    Args:
        input_str: URL or IA identifier

    Returns:
        Tuple of (ia_id, page_number or None, page_type or None)
        page_type is 'leaf' (physical scan order) or 'book' (printed page number)
    """
    ia_id = extract_ia_id(input_str)  # Use existing function for IA ID extraction

    # Check for page info in URL
    page_num = None
    page_type = None
    if '/page/' in input_str:
        try:
            # Format: /page/leaf5/, /page/n5/, or /page/42/
            page_part = input_str.split('/page/')[-1].rstrip('/')
            # Check if 'leaf' prefix is present
            if page_part.startswith('leaf'):
                page_type = 'leaf'
                page_part = page_part[4:]  # Remove 'leaf' prefix
            # Treat 'n' prefix as leaf for backwards compatibility
            elif page_part.startswith('n'):
                page_type = 'leaf'
                page_part = page_part[1:]  # Remove 'n' prefix
            else:
                # Bare number is a book page reference
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


def get_leaf_num(page_num: int, page_type: str,
                 ia_id: Optional[str] = None,
                 db: Optional[sqlite_utils.Database] = None) -> int:
    """Convert a page reference to a leaf number.

    Leaf numbers map directly to JP2 files and image API URLs:
    - leaf N = _{N:04d}.jp2
    - leaf N = leaf{N}_medium.jpg

    Args:
        page_num: The page number
        page_type: 'leaf' (use directly) or 'book' (lookup required)
        ia_id: Internet Archive identifier (needed for book page lookups)
        db: Optional sqlite_utils Database object (uses page_numbers table if available)

    Returns:
        Leaf number for image fetching

    Raises:
        ValueError: If conversion fails
    """
    if page_type == 'leaf':
        # Leaf number is the canonical format - use directly
        return page_num

    elif page_type == 'book':
        # Book page numbers need to be looked up in page_numbers table
        if db:
            try:
                result = db.execute(
                    "SELECT leaf_num FROM page_numbers WHERE book_page_number = ?",
                    [str(page_num)]
                ).fetchone()
                if result:
                    return result[0]
                else:
                    raise ValueError(f"Book page '{page_num}' not found in page_numbers table")
            except Exception as e:
                raise ValueError(f"Could not look up book page '{page_num}': {e}")
        elif ia_id:
            # Download page_numbers.json on the fly
            try:
                page_data = ia_client.download_json(ia_id, f"{ia_id}_page_numbers.json")
                if page_data and 'pages' in page_data:
                    for page_entry in page_data['pages']:
                        if page_entry.get('pageNumber') == str(page_num):
                            return page_entry['leafNum']
                raise ValueError(f"Book page '{page_num}' not found in page_numbers.json")
            except Exception as e:
                raise ValueError(f"Could not look up book page '{page_num}': {e}")
        else:
            raise ValueError("Book page lookup requires either index database or IA ID")

    else:
        raise ValueError(f"Unknown page_type: {page_type}. Use 'leaf' or 'book'.")


def parse_page_range(range_str: str, max_page: int | None = None) -> List[int]:
    """Parse page range string into list of page numbers.

    Supports formats:
    - Single page: '42'
    - Range: '1-7' (inclusive)
    - From start: '-10' (pages 1-10)
    - To end: '200-' (pages 200 to max_page, requires max_page)
    - Comma-separated: '1,3,5'
    - Mixed: '1-7,21,25-'

    Args:
        range_str: Page range string
        max_page: Maximum page number (required for open-ended ranges like '200-')

    Returns:
        Sorted list of unique integers

    Raises:
        ValueError: If format is invalid or max_page needed but not provided
    """
    pages = set()

    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue

        if '-' in part:
            # Range format: "1-7", "-10", or "200-"
            try:
                # Split only on first hyphen to handle negative-like syntax
                if part.startswith('-'):
                    # "-10" means 1 to 10
                    end = int(part[1:].strip())
                    start = 1
                elif part.endswith('-'):
                    # "200-" means 200 to max
                    start = int(part[:-1].strip())
                    if max_page is None:
                        raise ValueError(f"Open-ended range '{part}' requires max_page")
                    end = max_page
                else:
                    # "1-7" normal range
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
