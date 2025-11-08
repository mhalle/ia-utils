"""Page numbering and range parsing utilities."""

from typing import List, Optional, Tuple
import sqlite_utils


def parse_page_range(range_str: str) -> List[int]:
    """Parse page range string into list of page numbers.

    Supports formats:
    - Single page: '42'
    - Range: '1-7' (inclusive)
    - Comma-separated: '1,3,5'
    - Mixed: '1-7,21,25,45-50'

    Returns:
        Sorted list of unique integers
    """
    # TODO: Implement page range parsing
    pass


def get_page_number_for_jp2(page_num: int, page_type: str,
                            ia_id: Optional[str] = None,
                            db: Optional[sqlite_utils.Database] = None) -> int:
    """Convert from leaf/book page to sequential page number for jp2 files.

    Args:
        page_num: The page number in the specified format
        page_type: 'page' (sequential), 'leaf' (physical page), or 'book' (book page number)
        ia_id: Internet Archive identifier (needed for book/leaf lookups)
        db: Optional sqlite_utils Database object (uses page_numbers table if available)

    Returns:
        The sequential page number (1-indexed) for the jp2 filename
    """
    # TODO: Implement page number conversion
    pass


def extract_ia_id_and_page(input_str: str) -> Tuple[str, Optional[int], Optional[str]]:
    """Extract IA ID and optional page number from URL or ID string.

    Returns:
        Tuple of (ia_id, page_number or None, page_type or None)
    """
    # TODO: Implement IA ID and page extraction
    pass
