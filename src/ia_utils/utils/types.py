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
    word_count: int
    avg_confidence: Optional[int]
    avg_font_size: Optional[int]
    parent_carea_id: Optional[str]


@dataclass
class DocumentMetadata:
    """Metadata for an Internet Archive document."""
    slug: str
    ia_identifier: str
    title: str
    creator_primary: str
    creator_secondary: str
    publisher: str
    publication_date: str
    page_count: int
    language: str  # semicolon-separated if multiple
    ark_identifier: str
    oclc_id: str
    openlibrary_edition: str
    openlibrary_work: str
    scan_quality_ppi: int
    scan_camera: str
    scan_date: str
    collection: str  # semicolon-separated if multiple
    subject: str  # semicolon-separated if multiple
    mediatype: str
    contributor: str
    ocr: str
    description: str  # pipe-separated if multiple
