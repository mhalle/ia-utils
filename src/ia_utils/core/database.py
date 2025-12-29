"""SQLite database operations for catalogs."""

from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
import sqlite_utils

from ia_utils.utils.logger import Logger

# Type for catalog mode
CatalogMode = Literal['searchtext', 'mixed', 'hocr']


def get_document_metadata(db: sqlite_utils.Database) -> Dict[str, str]:
    """Read document_metadata key-value table as a dict."""
    if 'document_metadata' not in db.table_names():
        return {}
    return {row['key']: row['value'] for row in db['document_metadata'].rows}


def get_catalog_metadata(db: sqlite_utils.Database) -> Dict[str, str]:
    """Read catalog_metadata key-value table as a dict."""
    if 'catalog_metadata' not in db.table_names():
        return {}
    return {row['key']: row['value'] for row in db['catalog_metadata'].rows}


def build_fts_indexes(db: sqlite_utils.Database) -> None:
    """Build FTS indexes for text_blocks and pages."""
    # === BLOCK-LEVEL FTS INDEX ===
    db.executescript("""
        DROP TRIGGER IF EXISTS text_blocks_ai;
        DROP TRIGGER IF EXISTS text_blocks_ad;
        DROP TRIGGER IF EXISTS text_blocks_au;
        DROP TABLE IF EXISTS text_blocks_fts;
    """)
    db['text_blocks'].enable_fts(['text'], create_triggers=True)

    # === PAGE-LEVEL FTS INDEX ===
    db.executescript("""
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_insert;
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_update;
        DROP TRIGGER IF EXISTS rebuild_pages_fts_after_delete;
        DROP TABLE IF EXISTS pages_fts;

        CREATE VIRTUAL TABLE pages_fts USING fts5(
            page_text,
            page_id UNINDEXED
        );

        INSERT INTO pages_fts(rowid, page_text, page_id)
        SELECT
            ROW_NUMBER() OVER (ORDER BY page_id),
            group_concat(text, ' '),
            page_id
        FROM text_blocks
        GROUP BY page_id;

        CREATE TRIGGER rebuild_pages_fts_after_insert AFTER INSERT ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;

        CREATE TRIGGER rebuild_pages_fts_after_update AFTER UPDATE ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;

        CREATE TRIGGER rebuild_pages_fts_after_delete AFTER DELETE ON text_blocks
        BEGIN
            DELETE FROM pages_fts;
            INSERT INTO pages_fts(rowid, page_text, page_id)
            SELECT
                ROW_NUMBER() OVER (ORDER BY page_id),
                group_concat(text, ' '),
                page_id
            FROM text_blocks
            GROUP BY page_id;
        END;
    """)


def create_catalog_database(output_path: Path, ia_id: str, slug: str,
                           metadata: List[tuple], files: List[Dict],
                           blocks: List[Dict], page_numbers: Optional[Dict] = None,
                           catalog_mode: CatalogMode = 'hocr',
                           pages: Optional[List[Dict]] = None,
                           logger: Optional[Logger] = None) -> Path:
    """Create a new catalog database with all tables and indexes.

    Args:
        output_path: Path to write SQLite database
        ia_id: Internet Archive identifier
        slug: Human-readable slug for catalog
        metadata: Document metadata as list of (key, value) tuples
        files: List of archive files
        blocks: List of text blocks from hOCR or searchtext
        page_numbers: Optional page number mappings
        catalog_mode: 'searchtext', 'mixed', or 'hocr'
        pages: Optional page offset info for enrichment (searchtext mode)
        logger: Optional logger instance

    Returns:
        Path to created database
    """
    if logger is None:
        logger = Logger(verbose=False)

    output_path = Path(output_path)
    logger.info(f"\n   Building database: {output_path.name}")

    db = sqlite_utils.Database(output_path)

    # Drop existing tables for clean recreation
    for table in ['text_blocks_fts', 'pages_fts', 'text_blocks', 'pages',
                  'page_numbers', 'archive_files', 'document_metadata', 'catalog_metadata']:
        db[table].drop(ignore=True)

    # === TABLE 1: CATALOG METADATA (our computed fields) ===
    logger.progress("     Creating catalog_metadata...", nl=False)

    catalog_records = [
        {'key': 'slug', 'value': slug},
        {'key': 'created_at', 'value': datetime.now().isoformat()},
        {'key': 'catalog_mode', 'value': catalog_mode},
    ]
    db['catalog_metadata'].insert_all(catalog_records, pk='key', replace=True)
    logger.progress_done("✓")

    # === TABLE 2: DOCUMENT METADATA (from IA) ===
    logger.progress("     Creating document_metadata...", nl=False)

    # Convert metadata list of tuples to key-value records, joining multi-value fields
    metadata_dict: Dict[str, str] = {}
    for key, value in metadata:
        if key in metadata_dict:
            # Multi-value field: join with separator
            metadata_dict[key] = f"{metadata_dict[key]}; {value}"
        else:
            metadata_dict[key] = str(value)

    metadata_records = [{'key': k, 'value': v} for k, v in metadata_dict.items()]
    db['document_metadata'].insert_all(metadata_records, pk='key', replace=True)
    logger.progress_done("✓")

    # === TABLE 3: ARCHIVE FILES ===
    logger.progress("     Creating archive_files...", nl=False)

    files_records = []
    for file_info in files:
        files_records.append({
            'filename': file_info['filename'],
            'format': file_info['format'],
            'size_bytes': file_info['size'],
            'source_type': file_info['source'],
            'md5_checksum': file_info['md5'],
            'sha1_checksum': file_info['sha1'],
            'crc32_checksum': file_info['crc32'],
            'download_url': f'https://archive.org/download/{ia_id}/{file_info["filename"]}',
        })

    db['archive_files'].insert_all(files_records, pk='filename', replace=True)
    logger.progress_done(f"✓ ({len(files)} files)")

    # === TABLE 4: TEXT BLOCKS ===
    logger.progress("     Creating text_blocks...", nl=False)

    # For searchtext mode, blocks don't have hocr_id, use composite key
    if catalog_mode == 'searchtext':
        db['text_blocks'].insert_all(blocks, pk=['page_id', 'block_number'], replace=True)
    else:
        db['text_blocks'].insert_all(blocks, pk='hocr_id', replace=True)
    logger.progress_done(f"✓ ({len(blocks)} blocks)")

    # === TABLE 5: PAGES (for searchtext enrichment) ===
    if pages:
        logger.progress("     Creating pages...", nl=False)
        db['pages'].insert_all(pages, pk='page_id', replace=True)
        logger.progress_done(f"✓ ({len(pages)} pages)")

    # === TABLE 6: PAGE NUMBERS (MAPPING) ===
    if page_numbers and 'pages' in page_numbers:
        logger.progress("     Creating page_numbers...", nl=False)

        page_records = []
        for page_info in page_numbers['pages']:
            page_records.append({
                'leaf_num': page_info['leafNum'],
                'book_page_number': page_info.get('pageNumber', ''),
                'confidence': page_info.get('confidence'),
                'pageProb': page_info.get('pageProb'),
                'wordConf': page_info.get('wordConf'),
            })

        db['page_numbers'].insert_all(
            page_records,
            pk='leaf_num',
            replace=True,
        )
        logger.progress_done(f"✓ ({len(page_records)} page mappings)")

    # === INDEXES ===
    logger.progress("     Creating indexes...", nl=False)

    db.executescript("CREATE INDEX IF NOT EXISTS idx_page ON text_blocks(page_id);")
    if catalog_mode != 'searchtext':
        # These columns only exist in hocr/mixed mode
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_block_type ON text_blocks(block_type);
            CREATE INDEX IF NOT EXISTS idx_language ON text_blocks(language);
            CREATE INDEX IF NOT EXISTS idx_confidence ON text_blocks(avg_confidence);
            CREATE INDEX IF NOT EXISTS idx_font_size ON text_blocks(avg_font_size);
        """)
    if page_numbers:
        db.executescript("CREATE INDEX IF NOT EXISTS idx_book_page ON page_numbers(book_page_number);")
    logger.progress_done("✓")

    # === FTS INDEXES ===
    logger.progress("     Creating FTS indexes...", nl=False)
    build_fts_indexes(db)
    logger.progress_done("✓")

    # === STATISTICS ===
    blocks_count = db['text_blocks'].count
    pages_count = db.execute('SELECT COUNT(DISTINCT page_id) FROM text_blocks').fetchone()[0]
    avg_length = db.execute('SELECT AVG(length) FROM text_blocks').fetchone()[0]

    size_mb = output_path.stat().st_size / 1024 / 1024

    logger.info(f"\n   Database: {output_path.name}")
    logger.info(f"   Mode: {catalog_mode}")
    logger.info(f"   Size: {size_mb:.1f} MB")
    logger.info(f"   Records: {blocks_count} text blocks across {pages_count} pages")
    logger.info(f"   Average block length: {avg_length:.1f} chars" if avg_length else "   Average block length: N/A")

    # Only show hocr-specific stats if available
    if catalog_mode != 'searchtext':
        avg_conf_result = db.execute('SELECT AVG(avg_confidence) FROM text_blocks').fetchone()[0]
        avg_conf = avg_conf_result if avg_conf_result else 0
        logger.info(f"   OCR Quality: {avg_conf:.0f}% average confidence")

        # Block type breakdown
        type_stats = list(db.execute("""
            SELECT block_type, COUNT(*) as count
            FROM text_blocks
            GROUP BY block_type
            ORDER BY count DESC
        """))

        if type_stats:
            logger.info("\n   Block types:")
            for row in type_stats:
                logger.info(f"     {row[0]}: {row[1]}")

        # Language breakdown
        lang_stats = list(db.execute("""
            SELECT language, COUNT(*) as count
            FROM text_blocks
            WHERE language IS NOT NULL
            GROUP BY language
            ORDER BY count DESC
        """))

        if lang_stats:
            logger.info("\n   Languages:")
            for row in lang_stats:
                logger.info(f"     {row[0]}: {row[1]}")

    return output_path


def rebuild_text_blocks(db: sqlite_utils.Database, ia_id: str, hocr_filename: str,
                       logger: Optional[Logger] = None) -> int:
    """Rebuild text_blocks table from hOCR file.

    Args:
        db: SQLite database
        ia_id: Internet Archive identifier
        hocr_filename: Filename of hOCR file
        logger: Optional logger instance

    Returns:
        Number of blocks inserted
    """
    if logger is None:
        logger = Logger(verbose=False)

    from ia_utils.core import ia_client, parser

    logger.progress("   Downloading hOCR...", nl=False)
    hocr_bytes = ia_client.download_file(ia_id, hocr_filename, logger=logger, verbose=False)
    logger.progress_done("✓")

    blocks_list = parser.parse_hocr(hocr_bytes, logger=logger)

    logger.progress("   Inserting into text_blocks...", nl=False)
    db['text_blocks'].drop(ignore=True)
    db['text_blocks'].insert_all(
        blocks_list,
        pk='hocr_id',
        replace=True,
    )
    logger.progress_done("✓")

    return len(blocks_list)
