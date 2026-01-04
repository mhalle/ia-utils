"""Internet Archive API client operations."""

from typing import Optional, Dict, Any, Iterable, List
import asyncio
import gzip
import json
import httpx
import internetarchive as ia

from ia_utils.utils.logger import Logger

# File suffixes for IA derivative files
HOCR_SUFFIX = "_hocr.html"
SEARCHTEXT_SUFFIX = "_hocr_searchtext.txt.gz"
PAGEINDEX_SUFFIX = "_hocr_pageindex.json.gz"
META_SUFFIX = "_meta.xml"
FILES_SUFFIX = "_files.xml"

# Default timeout for HTTP requests
DEFAULT_TIMEOUT = 120.0


def get_item(ia_id: str) -> ia.Item:
    """Get an Internet Archive item.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Item object

    Raises:
        Exception: If item cannot be fetched
    """
    try:
        return ia.get_item(ia_id)
    except Exception as e:
        raise Exception(f"Failed to fetch item {ia_id}: {e}")


async def download_file_direct_async(
    client: httpx.AsyncClient,
    ia_id: str,
    filename: str,
) -> bytes:
    """Download a file directly without verification (async).

    Args:
        client: httpx async client
        ia_id: Internet Archive identifier
        filename: Name of file to download

    Returns:
        File bytes
    """
    url = f"https://archive.org/download/{ia_id}/{filename}"
    response = await client.get(url)
    response.raise_for_status()
    return response.content


def download_file_direct(ia_id: str, filename: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """Download a file directly without verification (sync).

    Use when you've already confirmed the file exists (e.g., from files.xml).

    Args:
        ia_id: Internet Archive identifier
        filename: Name of file to download
        timeout: Request timeout in seconds

    Returns:
        File bytes
    """
    url = f"https://archive.org/download/{ia_id}/{filename}"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def download_file(ia_id: str, filename: str, logger: Optional[Logger] = None,
                 verbose: bool = True) -> bytes:
    """Download a file from Internet Archive and return bytes.

    Uses internetarchive library to verify file exists, then downloads via httpx
    for in-memory access.

    Args:
        ia_id: Internet Archive identifier
        filename: Name of file to download
        logger: Optional logger instance
        verbose: Whether to print progress

    Returns:
        File bytes

    Raises:
        Exception: If download fails
    """
    if logger is None:
        logger = Logger(verbose=verbose)

    try:
        item = get_item(ia_id)
        file_obj = item.get_file(filename)

        if file_obj is None:
            raise FileNotFoundError(f"File {filename} not found in {ia_id}")

        if verbose:
            logger.progress(f"   Downloading {filename}...", nl=False)

        content = download_file_direct(ia_id, filename)

        if verbose:
            size_mb = len(content) / 1024 / 1024
            logger.progress_done(f"✓ ({size_mb:.1f} MB)")

        return content

    except Exception as e:
        if verbose:
            logger.progress_fail("✗")
        logger.error(f"Failed to download {filename}: {e}")
        raise


def download_json(ia_id: str, filename: str, logger: Optional[Logger] = None,
                 verbose: bool = False) -> Optional[Dict]:
    """Download a JSON file from Internet Archive.

    Returns None if download fails.

    Args:
        ia_id: Internet Archive identifier
        filename: Name of JSON file to download
        logger: Optional logger instance
        verbose: Whether to print warnings

    Returns:
        Parsed JSON data or None if download fails
    """
    if logger is None:
        logger = Logger(verbose=verbose)

    try:
        file_bytes = download_file(ia_id, filename, logger=logger, verbose=False)
        return json.loads(file_bytes.decode('utf-8'))
    except Exception as e:
        if verbose:
            logger.warning(f"Could not download {filename}: {e}")
        return None


def get_metadata(ia_id: str) -> Dict[str, Any]:
    """Fetch metadata from Internet Archive item.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Metadata dictionary
    """
    item = get_item(ia_id)
    return item.metadata


def get_files(ia_id: str) -> list:
    """Get list of files from Internet Archive item.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        List of file dictionaries
    """
    item = get_item(ia_id)
    return item.files


def search_items(query: str,
                 *,
                 fields: Optional[Iterable[str]] = None,
                 sorts: Optional[Iterable[str]] = None,
                 page: int = 1,
                 rows: int = 20,
                 params: Optional[Dict[str, Any]] = None,
                 full_text_search: bool = False,
                 logger: Optional[Logger] = None,
                 verbose: bool = False) -> Dict[str, Any]:
    """Search Archive.org items with pagination support.

    Args:
        query: Advancedsearch query string (Lucene syntax).
        fields: Metadata fields to include in results.
        sorts: Sort expressions (e.g. "date desc").
        page: Page number (1-indexed).
        rows: Number of rows per page.
        params: Additional query parameters passed to IA.
        full_text_search: Search inside book text (FTS) instead of metadata.
        logger: Optional logger for diagnostics.
        verbose: Whether to emit verbose progress messages.

    Returns:
        Dict with total hit count, requested page metadata, and result rows.
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if rows < 1:
        raise ValueError("rows must be >= 1")

    if logger is None:
        logger = Logger(verbose=verbose)

    base_params: Dict[str, Any] = {'page': page, 'rows': rows}
    if params:
        base_params.update(params)

    try:
        if verbose:
            logger.progress(f"Searching Internet Archive (page {page}, rows {rows})...", nl=False)
        search = ia.search_items(
            query,
            fields=list(fields) if fields else None,
            sorts=list(sorts) if sorts else None,
            params=base_params,
            full_text_search=full_text_search
        )
        results: List[Dict[str, Any]] = []
        for idx, item in enumerate(search):
            results.append(item)
            if idx + 1 >= rows:
                break
        total = getattr(search, 'num_found', len(results))
        if verbose:
            logger.progress_done(f"✓ ({total} total)")
        return {
            'query': query,
            'page': page,
            'rows': rows,
            'total': total,
            'results': results,
        }
    except Exception as exc:
        if verbose:
            logger.progress_fail()
        logger.error(f"Internet Archive search failed: {exc}")
        raise


def download_gzipped(ia_id: str, filename: str, logger: Optional[Logger] = None,
                     verbose: bool = True) -> bytes:
    """Download a gzipped file from Internet Archive and return decompressed bytes.

    Args:
        ia_id: Internet Archive identifier
        filename: Name of gzipped file to download
        logger: Optional logger instance
        verbose: Whether to print progress

    Returns:
        Decompressed file bytes

    Raises:
        Exception: If download fails
    """
    compressed = download_file(ia_id, filename, logger=logger, verbose=verbose)
    return gzip.decompress(compressed)


def file_exists(ia_id: str, filename: str) -> bool:
    """Check if a file exists in an Internet Archive item.

    Args:
        ia_id: Internet Archive identifier
        filename: Name of file to check

    Returns:
        True if file exists, False otherwise
    """
    try:
        item = get_item(ia_id)
        return item.get_file(filename) is not None
    except Exception:
        return False


def get_searchtext_files(ia_id: str) -> tuple:
    """Get filenames for searchtext and pageindex files.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Tuple of (searchtext_filename, pageindex_filename)
    """
    return (f"{ia_id}{SEARCHTEXT_SUFFIX}", f"{ia_id}{PAGEINDEX_SUFFIX}")


async def download_parallel_async(
    ia_id: str,
    downloads: List[Dict[str, Any]],
    logger: Optional[Logger] = None,
    verbose: bool = True,
    max_concurrent: int = 10,
) -> Dict[str, Any]:
    """Download multiple files in parallel using async httpx.

    Args:
        ia_id: Internet Archive identifier
        downloads: List of dicts with 'key', 'filename', and optional 'gzipped', 'json', 'optional' flags
        logger: Optional logger instance
        verbose: Whether to print progress
        max_concurrent: Maximum concurrent downloads

    Returns:
        Dict mapping key to downloaded content (bytes, str, or dict depending on flags)
    """
    if logger is None:
        logger = Logger(verbose=verbose)

    results = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch(client: httpx.AsyncClient, item: Dict[str, Any]) -> tuple:
        key = item['key']
        filename = item['filename']
        async with semaphore:
            try:
                content = await download_file_direct_async(client, ia_id, filename)
                if item.get('gzipped'):
                    content = gzip.decompress(content)
                if item.get('json'):
                    content = json.loads(content.decode('utf-8'))
                return (key, content, None)
            except Exception as e:
                if item.get('optional'):
                    return (key, None, None)
                return (key, None, e)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True, http2=True) as client:
        tasks = [fetch(client, item) for item in downloads]
        fetch_results = await asyncio.gather(*tasks)

    for key, content, error in fetch_results:
        if error:
            raise error
        results[key] = content

    return results


def download_parallel(
    ia_id: str,
    downloads: List[Dict[str, Any]],
    logger: Optional[Logger] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """Download multiple files in parallel (sync wrapper).

    Args:
        ia_id: Internet Archive identifier
        downloads: List of dicts with 'key', 'filename', and optional 'gzipped', 'json' flags
        logger: Optional logger instance
        verbose: Whether to print progress

    Returns:
        Dict mapping key to downloaded content (bytes, str, or dict depending on flags)
    """
    return asyncio.run(download_parallel_async(ia_id, downloads, logger, verbose))


async def download_images_async(
    ia_id: str,
    pages: List[int],
    size: str = 'medium',
    max_concurrent: int = 16,
) -> List[tuple]:
    """Download multiple page images in parallel.

    Args:
        ia_id: Internet Archive identifier
        pages: List of leaf numbers to download
        size: Image size (small, medium, large)
        max_concurrent: Maximum concurrent downloads

    Returns:
        List of (filename, image_bytes) tuples
    """
    from ia_utils.core.image import get_api_image_url

    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def fetch_image(client: httpx.AsyncClient, leaf_num: int) -> tuple:
        async with semaphore:
            url = get_api_image_url(ia_id, leaf_num, size)
            response = await client.get(url)
            response.raise_for_status()
            filename = f"{ia_id}_{leaf_num:04d}.jpg"
            return (filename, response.content)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True, http2=True) as client:
        tasks = [fetch_image(client, leaf) for leaf in pages]
        results = await asyncio.gather(*tasks)

    return list(results)


def download_images(
    ia_id: str,
    pages: List[int],
    size: str = 'medium',
    max_concurrent: int = 16,
) -> List[tuple]:
    """Download multiple page images in parallel (sync wrapper).

    Args:
        ia_id: Internet Archive identifier
        pages: List of leaf numbers to download
        size: Image size (small, medium, large)
        max_concurrent: Maximum concurrent downloads

    Returns:
        List of (filename, image_bytes) tuples
    """
    return asyncio.run(download_images_async(ia_id, pages, size, max_concurrent))
