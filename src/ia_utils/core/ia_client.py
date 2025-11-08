"""Internet Archive API client operations."""

from typing import Optional, Dict, Any
import json
import requests
import internetarchive as ia

from ia_utils.utils.logger import Logger


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


def download_file(ia_id: str, filename: str, logger: Optional[Logger] = None,
                 verbose: bool = True) -> bytes:
    """Download a file from Internet Archive and return bytes.

    Uses internetarchive library to verify file exists, then downloads via requests
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

        # Build download URL from archive.org
        url = f"https://archive.org/download/{ia_id}/{filename}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        content = response.content

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
        List of file objects
    """
    item = get_item(ia_id)
    return item.files_list()
