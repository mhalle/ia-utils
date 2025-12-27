"""SQLite database operations for catalogs."""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import sqlite_utils

from ia_utils.utils.logger import Logger


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
                           metadata: Dict[str, Any], files: List[Dict],
                           blocks: List[Dict], page_numbers: Optional[Dict] = None,
                           logger: Optional[Logger] = None) -> Path:
    """Create a new catalog database with all tables and indexes.

    Args:
        output_path: Path to write SQLite database
        ia_id: Internet Archive identifier
        slug: Human-readable slug for catalog
        metadata: Document metadata
        files: List of archive files
        blocks: List of text blocks from hOCR
        page_numbers: Optional page number mappings
        logger: Optional logger instance

    Returns:
        Path to created database
    """
    if logger is None:
        logger = Logger(verbose=False)

    output_path = Path(output_path)
    logger.info(f"\n   Building database: {output_path.name}")

    db = sqlite_utils.Database(output_path)

    # === TABLE 1: DOCUMENT METADATA ===
    logger.progress("     Creating document_metadata...", nl=False)

    # Convert metadata list of tuples to helpers for single and multi-value access
    def get_first(key: str, default: str = '') -> str:
        """Get first value for a key."""
        for k, v in metadata:
            if k == key:
                return v
        return default

    def get_all(key: str) -> List[str]:
        """Get all values for a key (for multi-value fields)."""
        return [v for k, v in metadata if k == key]

    creators = get_all('creator')
    languages = get_all('language')
    collections = get_all('collection')
    subjects = get_all('subject')
    descriptions = get_all('description')

    creator_primary = creators[0] if creators else ''
    creator_secondary = creators[1] if len(creators) > 1 else ''

    imagecount = get_first('imagecount', '')
    ppi = get_first('ppi', '')

    metadata_record = {
        'slug': slug,
        'ia_identifier': ia_id,
        'title': get_first('title'),
        'creator_primary': creator_primary,
        'creator_secondary': creator_secondary,
        'publisher': get_first('publisher'),
        'publication_date': get_first('date'),
        'page_count': int(imagecount) if imagecount.isdigit() else 0,
        'language': '; '.join(languages) if languages else 'eng',
        'ark_identifier': get_first('identifier-ark'),
        'oclc_id': get_first('oclc-id'),
        'openlibrary_edition': get_first('openlibrary_edition'),
        'openlibrary_work': get_first('openlibrary_work'),
        'scan_quality_ppi': int(ppi) if ppi.isdigit() else 400,
        'scan_camera': get_first('camera'),
        'scan_date': get_first('scandate'),
        'collection': '; '.join(collections) if collections else '',
        'subject': '; '.join(subjects) if subjects else '',
        'mediatype': get_first('mediatype'),
        'contributor': get_first('contributor'),
        'ocr': get_first('ocr'),
        'description': ' | '.join(descriptions) if descriptions else '',
        'created_at': datetime.now().isoformat(),
    }

    db['document_metadata'].insert(metadata_record, pk='id', replace=True)
    logger.progress_done("✓")

    # === TABLE 2: ARCHIVE FILES ===
    logger.progress("     Creating archive_files...", nl=False)

    files_records = []
    for file_info in files:
        files_records.append({
            'document_id': 1,
            'filename': file_info['filename'],
            'format': file_info['format'],
            'size_bytes': file_info['size'],
            'source_type': file_info['source'],
            'md5_checksum': file_info['md5'],
            'sha1_checksum': file_info['sha1'],
            'crc32_checksum': file_info['crc32'],
            'download_url': f'https://archive.org/download/{ia_id}/{file_info["filename"]}',
            'created_at': datetime.now().isoformat(),
        })

    db['archive_files'].insert_all(files_records, foreign_keys=[('document_id', 'document_metadata', 'id')])
    logger.progress_done(f"✓ ({len(files)} files)")

    # === TABLE 3: TEXT BLOCKS ===
    logger.progress("     Creating text_blocks...", nl=False)

    db['text_blocks'].insert_all(
        blocks,
        pk='hocr_id',
        replace=True,
    )
    logger.progress_done(f"✓ ({len(blocks)} blocks)")

    # === TABLE 4: PAGE NUMBERS (MAPPING) ===
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

    # === TABLE 5: INDEXES ===
    logger.progress("     Creating indexes...", nl=False)

    db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_page ON text_blocks(page_id);
        CREATE INDEX IF NOT EXISTS idx_block_type ON text_blocks(block_type);
        CREATE INDEX IF NOT EXISTS idx_language ON text_blocks(language);
        CREATE INDEX IF NOT EXISTS idx_confidence ON text_blocks(avg_confidence);
        CREATE INDEX IF NOT EXISTS idx_font_size ON text_blocks(avg_font_size);
        CREATE INDEX IF NOT EXISTS idx_book_page ON page_numbers(book_page_number);
    """)
    logger.progress_done("✓")

    # === TABLES 6-7: FTS INDEXES ===
    logger.progress("     Creating FTS indexes...", nl=False)
    build_fts_indexes(db)
    logger.progress_done("✓")

    # === STATISTICS ===
    blocks_count = db['text_blocks'].count
    pages_count = db.execute('SELECT COUNT(DISTINCT page_id) FROM text_blocks').fetchone()[0]
    avg_conf_result = db.execute('SELECT AVG(avg_confidence) FROM text_blocks').fetchone()[0]
    avg_conf = avg_conf_result if avg_conf_result else 0
    avg_words = db.execute('SELECT AVG(word_count) FROM text_blocks').fetchone()[0]

    size_mb = output_path.stat().st_size / 1024 / 1024

    logger.info(f"\n   Database: {output_path.name}")
    logger.info(f"   Size: {size_mb:.1f} MB")
    logger.info(f"   Records: {blocks_count} text blocks across {pages_count} pages")
    logger.info(f"   Average words per block: {avg_words:.1f}" if avg_words else "   Average words per block: N/A")
    logger.info(f"   OCR Quality: {avg_conf:.0f}% average confidence")

    # Block type breakdown
    logger.info("\n   Block types:")
    type_stats = list(db.execute("""
        SELECT block_type, COUNT(*) as count
        FROM text_blocks
        GROUP BY block_type
        ORDER BY count DESC
    """))

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
