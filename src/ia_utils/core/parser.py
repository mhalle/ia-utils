"""hOCR and metadata parsing utilities."""

from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
import re
from statistics import mean
from bs4 import BeautifulSoup, Tag

from ia_utils.utils.logger import Logger


def parse_metadata(meta_bytes: bytes) -> Dict[str, str]:
    """Parse meta.xml bytes into metadata dictionary."""
    root = ET.fromstring(meta_bytes)
    metadata = {}
    for child in root:
        metadata[child.tag] = child.text
    return metadata


def parse_files(files_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse files.xml bytes into list of file dictionaries."""
    root = ET.fromstring(files_bytes)
    files = []

    for file_elem in root.findall('file'):
        filename = file_elem.get('name', '')
        format_elem = file_elem.find('format')
        size_elem = file_elem.find('size')
        source = file_elem.get('source', '')
        md5 = file_elem.find('md5')
        sha1 = file_elem.find('sha1')
        crc32 = file_elem.find('crc32')

        files.append({
            'filename': filename,
            'format': format_elem.text if format_elem is not None else '',
            'size': int(size_elem.text) if size_elem is not None else 0,
            'source': source,
            'md5': md5.text if md5 is not None else '',
            'sha1': sha1.text if sha1 is not None else '',
            'crc32': crc32.text if crc32 is not None else '',
        })

    return files


def parse_bbox(title_str: str) -> Tuple[Optional[int], ...]:
    """Extract bbox coordinates from hOCR title attribute."""
    match = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', title_str)
    if match:
        return tuple(map(int, match.groups()))
    return (None, None, None, None)


def parse_confidence(title_str: str) -> Optional[int]:
    """Extract x_wconf from title attribute."""
    match = re.search(r'x_wconf (\d+)', title_str)
    return int(match.group(1)) if match else None


def parse_font_size(title_str: str) -> Optional[int]:
    """Extract x_fsize from title attribute."""
    match = re.search(r'x_fsize (\d+)', title_str)
    return int(match.group(1)) if match else None


def extract_plain_text(block: Tag) -> str:
    """Extract all text content from block, removing HTML markup."""
    words = block.find_all(class_='ocrx_word')
    word_texts = [word.get_text(strip=True) for word in words]
    return ' '.join(word_texts)


def get_block_type(block: Tag) -> str:
    """Determine block type from CSS classes."""
    classes = block.get('class', [])

    # Handle both string (XML parser) and list (HTML parser)
    if isinstance(classes, str):
        classes = classes.split()

    ocr_classes = [c for c in classes if c.startswith('ocr_')]
    return ocr_classes[0] if ocr_classes else 'unknown'


def sort_blocks_by_position(blocks: List[Tag]) -> List[Tag]:
    """Sort blocks by visual position (top-to-bottom, left-to-right)."""
    def get_position(block):
        title = block.get('title', '')
        bbox = parse_bbox(title)
        return (bbox[1] or 0, bbox[0] or 0)  # (y0, x0)

    return sorted(blocks, key=get_position)


def extract_page_id(page: Tag) -> str:
    """Extract page ID from hOCR page element."""
    page_id = page.get('id', '')
    match = re.search(r'page_(\d+)', page_id)
    return match.group(1) if match else ''


def extract_parent_carea_id(block: Tag) -> Optional[str]:
    """Find parent column area ID (carea)."""
    parent = block.parent
    while parent and parent.name != 'div':
        parent = parent.parent
    if parent and 'ocr_carea' in (parent.get('class') or []):
        return parent.get('id')
    return None


def parse_hocr(hocr_bytes: bytes, logger: Optional[Logger] = None) -> List[Dict[str, Any]]:
    """Parse hOCR HTML bytes and extract text blocks.

    Args:
        hocr_bytes: Raw hOCR HTML bytes
        logger: Optional logger instance

    Returns:
        List of text block dictionaries
    """
    if logger is None:
        logger = Logger(verbose=False)

    logger.progress("   Parsing hOCR...", nl=False)

    hocr_content = hocr_bytes.decode('utf-8')
    soup = BeautifulSoup(hocr_content, 'xml')

    # Get all pages
    pages = soup.find_all(class_='ocr_page')
    total_blocks = 0
    blocks_list = []

    # Process each page
    for page_idx, page in enumerate(pages, 1):
        page_id = extract_page_id(page)

        # Get all text block types
        blocks = (
            page.find_all(class_='ocr_par') +
            page.find_all(class_='ocr_caption') +
            page.find_all(class_='ocr_header') +
            page.find_all(class_='ocr_textfloat')
        )

        # Sort blocks by position
        blocks = sort_blocks_by_position(blocks)

        # Process each block
        for block_number, block in enumerate(blocks):
            # Extract basic attributes
            hocr_id = block.get('id', '')
            block_type = get_block_type(block)
            language = block.get('lang') or block.get('xml:lang')
            text_direction = block.get('dir', 'ltr')

            # Parse bounding box
            title = block.get('title', '')
            bbox = parse_bbox(title)

            # Extract plain text
            text = extract_plain_text(block)

            # Only process blocks with actual text
            if not text.strip():
                continue

            # Find parent column area
            parent_carea_id = extract_parent_carea_id(block)

            # Compute statistics
            lines = block.find_all(class_='ocr_line')
            line_count = len(lines)

            words = block.find_all(class_='ocrx_word')
            word_count = len(words)

            # Average confidence from word-level x_wconf
            confidences = [
                parse_confidence(word.get('title', ''))
                for word in words
            ]
            confidences = [c for c in confidences if c is not None]
            avg_confidence = mean(confidences) if confidences else None

            # Average font size from word-level x_fsize
            font_sizes = [
                parse_font_size(word.get('title', ''))
                for word in words
            ]
            font_sizes = [f for f in font_sizes if f is not None]
            avg_font_size = mean(font_sizes) if font_sizes else None

            blocks_list.append({
                'page_id': page_id,
                'block_number': block_number,
                'hocr_id': hocr_id,
                'block_type': block_type,
                'language': language,
                'text_direction': text_direction,
                'bbox_x0': bbox[0],
                'bbox_y0': bbox[1],
                'bbox_x1': bbox[2],
                'bbox_y1': bbox[3],
                'text': text,
                'line_count': line_count,
                'word_count': word_count,
                'avg_confidence': avg_confidence,
                'avg_font_size': avg_font_size,
                'parent_carea_id': parent_carea_id,
            })
            total_blocks += 1

    logger.progress_done(f"✓ ({total_blocks} blocks)")
    return blocks_list
