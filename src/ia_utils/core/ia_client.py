"""Internet Archive API client operations."""

from typing import Optional, Dict, Any
from io import BytesIO
import internetarchive as ia
import requests

from ia_utils.utils.logger import Logger


def download_file(ia_id: str, filename: str, logger: Optional[Logger] = None,
                 verbose: bool = True) -> bytes:
    """Download a file from Internet Archive and return bytes.

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

    # Try using internetarchive library first
    try:
        item = ia.get_item(ia_id)
        file_obj = item.get_file(filename)

        if file_obj is None:
            raise FileNotFoundError(f"File {filename} not found in {ia_id}")

        # Download the file
        if verbose:
            logger.progress(f"   Downloading {filename}...", nl=False)

        # Use requests to download directly from archive.org
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
            logger.progress_fail(f"✗")
        logger.error(f"Failed to download {filename}: {e}")
        raise


def download_json(ia_id: str, filename: str, logger: Optional[Logger] = None,
                 verbose: bool = False) -> Optional[Dict]:
    """Download a JSON file from Internet Archive.

    Returns empty dict if download fails.
    """
    if logger is None:
        logger = Logger(verbose=verbose)

    try:
        url = f"https://archive.org/download/{ia_id}/{filename}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        if verbose:
            logger.warning(f"Could not download {filename}: {e}")
        return None


def get_item_metadata(ia_id: str) -> Dict[str, Any]:
    """Fetch metadata from Internet Archive item."""
    item = ia.get_item(ia_id)
    return item.metadata


def get_item_files(ia_id: str) -> list:
    """Get list of files from Internet Archive item."""
    item = ia.get_item(ia_id)
    return item.files_list()
