"""hOCR and metadata parsing utilities."""

from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
import re
from statistics import mean
from bs4 import BeautifulSoup, Tag

from ia_utils.utils.logger import Logger


def parse_metadata(meta_bytes: bytes) -> List[Tuple[str, str]]:
    """Parse meta.xml bytes into list of (key, value) tuples.

    Returns tuples instead of dict to preserve multiple values for the same key
    (e.g., multiple <language>, <collection>, <subject>, <description> tags).
    """
    root = ET.fromstring(meta_bytes)
    metadata = []
    for child in root:
        if child.text:
            metadata.append((child.tag, child.text))
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


def extract_page_id(page: Tag) -> int:
    """Extract page ID (leaf number) from hOCR page element."""
    page_id = page.get('id', '')
    match = re.search(r'page_(\d+)', page_id)
    return int(match.group(1)) if match else 0


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
            length = len(text)

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
                'length': length,
                'avg_confidence': avg_confidence,
                'avg_font_size': avg_font_size,
                'parent_carea_id': parent_carea_id,
            })
            total_blocks += 1

    logger.progress_done(f"✓ ({total_blocks} blocks)")
    return blocks_list


def parse_searchtext(searchtext_bytes: bytes) -> str:
    """Parse searchtext.txt.gz content into text string.

    Args:
        searchtext_bytes: Raw (decompressed) searchtext content

    Returns:
        Full text content as string
    """
    return searchtext_bytes.decode('utf-8')


def parse_pageindex(pageindex_bytes: bytes) -> List[Tuple[int, int, int, int]]:
    """Parse pageindex.json.gz content into list of page offset tuples.

    Args:
        pageindex_bytes: Raw (decompressed) JSON content

    Returns:
        List of tuples: (char_start, char_end, hocr_byte_start, hocr_byte_end)
        One tuple per page (leaf).
    """
    import json
    return [tuple(page) for page in json.loads(pageindex_bytes)]


def blocks_from_searchtext(
    searchtext_content: str,
    pageindex: List[Tuple[int, int, int, int]],
    logger: Optional[Logger] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build text_blocks and pages records from searchtext and pageindex.

    Args:
        searchtext_content: Full searchtext content as string
        pageindex: List of (char_start, char_end, hocr_byte_start, hocr_byte_end)
        logger: Optional logger instance

    Returns:
        Tuple of (text_blocks, pages) where:
        - text_blocks: List of dicts with page_id, block_number, text, length
        - pages: List of dicts with page_id, char_start, char_end, hocr_byte_start, hocr_byte_end
    """
    if logger is None:
        logger = Logger(verbose=False)

    logger.progress("   Parsing searchtext...", nl=False)

    text_blocks = []
    pages = []

    for page_id, (char_start, char_end, hocr_start, hocr_end) in enumerate(pageindex):
        pages.append({
            'page_id': page_id,
            'char_start': char_start,
            'char_end': char_end,
            'hocr_byte_start': hocr_start,
            'hocr_byte_end': hocr_end,
        })

        # Slice the page's text and split into lines
        page_text = searchtext_content[char_start:char_end]
        for block_number, line in enumerate(page_text.split('\n')):
            text = line.strip()
            if text:
                text_blocks.append({
                    'page_id': page_id,
                    'block_number': block_number,
                    'text': text,
                    'length': len(text),
                })

    logger.progress_done(f"✓ ({len(text_blocks)} blocks, {len(pages)} pages)")
    return text_blocks, pages


def parse_djvu_xml(
    djvu_bytes: bytes,
    logger: Optional[Logger] = None
) -> List[Dict[str, Any]]:
    """Parse DjVu XML bytes and extract text blocks.

    Uses streaming parser for memory efficiency with large files.

    Args:
        djvu_bytes: Raw DjVu XML bytes
        logger: Optional logger instance

    Returns:
        List of text block dictionaries compatible with hocr schema
    """
    from lxml import etree
    from io import BytesIO

    if logger is None:
        logger = Logger(verbose=False)

    logger.progress("   Parsing DjVu XML...", nl=False)

    blocks_list = []
    context = etree.iterparse(BytesIO(djvu_bytes), events=('end',), tag='OBJECT')

    for page_id, (event, obj) in enumerate(context):
        block_number = 0

        for para in obj.iter('PARAGRAPH'):
            # Extract words and confidence values
            words = []
            confidences = []
            for word in para.iter('WORD'):
                if word.text:
                    words.append(word.text)
                    conf = word.get('x-confidence')
                    if conf:
                        try:
                            confidences.append(int(conf))
                        except ValueError:
                            pass

            if not words:
                continue

            text = ' '.join(words)
            if not text.strip():
                continue

            # Count lines
            line_count = len(list(para.iter('LINE')))

            # Calculate average confidence
            avg_confidence = mean(confidences) if confidences else None

            # Generate hocr-compatible ID
            hocr_id = f"par_{page_id:06d}_{block_number:06d}"

            blocks_list.append({
                'page_id': page_id,
                'block_number': block_number,
                'hocr_id': hocr_id,
                'block_type': 'ocr_par',
                'language': None,
                'text_direction': None,
                'bbox_x0': None,
                'bbox_y0': None,
                'bbox_x1': None,
                'bbox_y1': None,
                'text': text,
                'line_count': line_count,
                'length': len(text),
                'avg_confidence': avg_confidence,
                'avg_font_size': None,
                'parent_carea_id': None,
            })
            block_number += 1

        # Free memory
        obj.clear()

    logger.progress_done(f"✓ ({len(blocks_list)} blocks)")
    return blocks_list
