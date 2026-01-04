"""Get URL command for page images and viewer."""

import sys
import webbrowser
import click
import sqlite_utils

from ia_utils.core.database import get_document_metadata
from ia_utils.utils.logger import Logger
from ia_utils.utils import pages as page_utils


def build_page_image_url(ia_id: str, leaf_num: int, size: str = 'original') -> str:
    """Build URL for a page image.

    Args:
        ia_id: Internet Archive identifier
        leaf_num: Leaf number (physical scan order)
        size: Image size (small, medium, large, original)

    Returns:
        URL string
    """
    if size == 'original':
        # Direct JP2 URL using ZIP-as-directory format
        return f"https://archive.org/download/{ia_id}/{ia_id}_jp2.zip/{ia_id}_jp2/{ia_id}_{leaf_num:04d}.jp2"
    else:
        # API URL for resized images
        return f"https://archive.org/download/{ia_id}/page/leaf{leaf_num}_{size}.jpg"


def build_viewer_url(ia_id: str, leaf_num: int = None) -> str:
    """Build URL for the IA book viewer, optionally at a specific page.

    Args:
        ia_id: Internet Archive identifier
        leaf_num: Leaf number (physical scan order), or None for item root

    Returns:
        URL string
    """
    if leaf_num is not None:
        return f"https://archive.org/details/{ia_id}/page/leaf{leaf_num}"
    return f"https://archive.org/details/{ia_id}"


def build_pdf_url(ia_id: str, leaf_num: int = None) -> str:
    """Build URL for the PDF, optionally at a specific page.

    Args:
        ia_id: Internet Archive identifier
        leaf_num: Leaf number (physical scan order), or None for base PDF URL

    Returns:
        URL string
    """
    base_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
    if leaf_num is not None:
        # PDF pages are 1-indexed, leaf numbers are 0-indexed
        pdf_page = leaf_num + 1
        return f"{base_url}#page={pdf_page}"
    return base_url


@click.command('get-url')
@click.argument('identifier', required=False)
@click.option('-l', '--leaf', type=int, help='Leaf number (physical scan order)')
@click.option('-b', '--book', type=int, help='Book page number (printed page, requires lookup)')
@click.option('-i', '--index', type=click.Path(exists=True), help='Index database path')
@click.option('--viewer', is_flag=True, help='Get viewer URL instead of image URL')
@click.option('--pdf', is_flag=True, help='Get PDF URL (with #page if page specified)')
@click.option('--size', type=click.Choice(['small', 'medium', 'large', 'original']),
              default='original', help='Image size (default: original, ignored with --viewer/--pdf)')
@click.option('--open', 'open_browser', is_flag=True, help='Open URL in web browser')
@click.pass_context
def get_url(ctx, identifier, leaf, book, index, viewer, pdf, size, open_browser):
    """Get URL for a page image, viewer, or PDF from Internet Archive.

    By default returns direct image URL. Use --viewer for book reader URL,
    or --pdf for PDF URL.

    IDENTIFIER (optional if -i provided):
    - IA ID: anatomicalatlasi00smit
    - URL: https://archive.org/details/anatomicalatlasi00smit
    - URL with page: https://archive.org/details/b31362138/page/leaf5/
    - Omit if using -i (index contains IA ID)

    PAGE NUMBER (optional for --viewer and --pdf):
    - Use -l/--leaf for physical scan number (direct, fast)
    - Use -b/--book for printed page number (requires lookup)
    - Can also extract from URL (/page/leafN/ or /page/N/)
    - Without page: --viewer returns item URL, --pdf returns base PDF URL

    IMAGE SIZES (for image URL, ignored with --viewer/--pdf):
    - small: ~300px width
    - medium: ~600px width
    - large: full resolution
    - original: full resolution JP2 (default)

    Examples:
        ia-utils get-url anatomicalatlasi00smit -l 5
        ia-utils get-url -i index.sqlite -l 5 --size large
        ia-utils get-url -i index.sqlite -b 42 --viewer
        ia-utils get-url -i index.sqlite --viewer
        ia-utils get-url -i index.sqlite --pdf
        ia-utils get-url -i index.sqlite -l 661 --pdf
    """
    verbose = ctx.obj.get('verbose', False)
    logger = Logger(verbose=verbose)

    # Extract IA ID and page info from identifier (if provided)
    ia_id = None
    page_from_url = None
    page_type_from_url = None
    if identifier:
        ia_id, page_from_url, page_type_from_url = page_utils.extract_ia_id_and_page(identifier)
        # Warn if identifier looks like a file path (IA identifiers don't contain / or .)
        if ia_id and ('/' in ia_id or '.' in ia_id):
            logger.warning(f"Identifier '{ia_id}' contains '/' or '.' - did you mean to use -i for an index?")
            sys.exit(1)

    # Load index if provided
    db = None
    if index:
        logger.verbose_info(f"Loading index: {index}")
        try:
            db = sqlite_utils.Database(index)
            doc_metadata = get_document_metadata(db)
            if not doc_metadata:
                logger.error("No metadata found in index database")
                sys.exit(1)
            ia_id_from_index = doc_metadata['identifier']
            # Verify IA ID matches if identifier was also provided
            if ia_id and ia_id != ia_id_from_index:
                logger.error(f"IA ID mismatch - Identifier: {ia_id}, Index: {ia_id_from_index}")
                sys.exit(1)
            ia_id = ia_id_from_index
        except Exception as e:
            logger.error(f"Failed to read index database: {e}")
            sys.exit(1)

    if not ia_id:
        logger.error("IDENTIFIER required (or use -i with index)")
        sys.exit(1)

    # Validate mutually exclusive options
    if leaf is not None and book is not None:
        logger.error("Cannot specify both --leaf and --book")
        sys.exit(1)

    if viewer and pdf:
        logger.error("Cannot specify both --viewer and --pdf")
        sys.exit(1)

    # Determine page number and type from flags or URL
    page_number_int = None
    num_type = None
    if leaf is not None:
        page_number_int = leaf
        num_type = 'leaf'
    elif book is not None:
        page_number_int = book
        num_type = 'book'
    elif page_from_url is not None:
        page_number_int = page_from_url
        num_type = page_type_from_url or 'leaf'

    # Page is required only for image URLs (not --viewer or --pdf)
    if page_number_int is None and not pdf and not viewer:
        logger.error("Page number required: use -l/--leaf or -b/--book (or provide URL with /page/...)")
        sys.exit(1)

    # Convert to leaf number if page was specified
    leaf_num = None
    if page_number_int is not None:
        try:
            leaf_num = page_utils.get_leaf_num(page_number_int, num_type, ia_id=ia_id, db=db)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    # Build and output URL
    if pdf:
        url = build_pdf_url(ia_id, leaf_num)
    elif viewer:
        url = build_viewer_url(ia_id, leaf_num)
    else:
        url = build_page_image_url(ia_id, leaf_num, size)

    click.echo(url)

    if open_browser:
        webbrowser.open(url)
