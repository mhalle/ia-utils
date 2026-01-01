"""Type hints and dataclasses for ia-utils."""

from dataclasses import dataclass
from typing import Optional, Literal


@dataclass
class TextBlock:
    """Represents a single text block from hOCR."""
    page_id: int
    block_number: int
    hocr_id: str
    block_type: str
    language: Optional[str]
    text_direction: str
    bbox_x0: Optional[int]
    bbox_y0: Optional[int]
    bbox_x1: Optional[int]
    bbox_y1: Optional[int]
    text: str
    line_count: int
    length: int  # non-whitespace character count
    avg_confidence: Optional[int]
    avg_font_size: Optional[int]
    parent_carea_id: Optional[str]


# NOTE: Index metadata uses official IA field names with dynamic columns.
# All fields from the IA item metadata are stored directly.
# Multi-value fields are joined with "; " separator.
# Common fields include:
#   identifier, title, creator, date, publisher, language, description,
#   collection, subject, mediatype, contributor, ocr, imagecount, ppi,
#   licenseurl, rights, possible-copyright-status, scandate, scanner, etc.
# Plus computed fields: slug, created_at
