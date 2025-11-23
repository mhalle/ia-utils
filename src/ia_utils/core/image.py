"""Image processing and fetching for page images."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Literal
from io import BytesIO
import requests
from remotezip import RemoteZip
from PIL import Image, ImageOps

from ia_utils.utils.logger import Logger


def get_server_from_metadata(ia_id: str) -> str:
    """Get the actual IA server hosting an item from metadata API.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Server hostname (e.g., 'ia800508.us.archive.org') or 'archive.org' as fallback
    """
    try:
        resp = requests.get(f'https://archive.org/metadata/{ia_id}', timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if 'server' in data:
            return data['server']
    except Exception:
        pass
    return 'archive.org'


class ImageSource(ABC):
    """Abstract base class for image sources."""

    @abstractmethod
    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch raw image bytes for a page."""
        pass


class APIImageSource(ImageSource):
    """Fetch images from Internet Archive API (small, medium, large)."""

    def __init__(self, size: Literal['small', 'medium', 'large'] = 'medium'):
        if size not in ('small', 'medium', 'large'):
            raise ValueError(f"Invalid API size: {size}")
        self.size = size

    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch image from IA page API.

        Args:
            ia_id: Internet Archive identifier
            page_num: Sequential page number (0-origin for API)

        Returns:
            Image bytes

        Raises:
            Exception: If download fails
        """
        # IA API uses 0-origin page numbering
        # URL format: https://archive.org/download/{id}/page/n{page_num}_{size}.jpg
        # Archive.org CDN handles routing to appropriate server efficiently
        url = f"https://archive.org/download/{ia_id}/page/n{page_num}_{self.size}.jpg"

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content


class JP2ImageSource(ImageSource):
    """Fetch images from jp2.zip using remotezip (original quality)."""

    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch image from JP2 archive.

        Args:
            ia_id: Internet Archive identifier
            page_num: Sequential page number (1-origin for JP2)

        Returns:
            Image bytes

        Raises:
            Exception: If download fails
        """
        # Format page number as 4-digit zero-padded for jp2 archive
        jp2_page_num = f"{page_num:04d}"
        jp2_filename = f"{ia_id}_{jp2_page_num}.jp2"
        # Files are stored in subdirectory {ia_id}_jp2/
        jp2_path_in_zip = f"{ia_id}_jp2/{jp2_filename}"

        # IA jp2.zip URL
        zip_url = f"https://archive.org/download/{ia_id}/{ia_id}_jp2.zip"

        try:
            # Use remotezip to fetch just this one file
            with RemoteZip(zip_url) as rz:
                # Check if file exists in zip (try both with and without subdirectory)
                file_in_zip = None
                if jp2_path_in_zip in rz.namelist():
                    file_in_zip = jp2_path_in_zip
                elif jp2_filename in rz.namelist():
                    file_in_zip = jp2_filename

                if not file_in_zip:
                    raise FileNotFoundError(f"Page {page_num} ({jp2_filename}) not found in archive")

                # Read the jp2 file into memory
                jp2_data = rz.read(file_in_zip)
                return jp2_data

        except Exception as e:
            raise Exception(f"Failed to fetch JP2 page {page_num}: {e}")


def process_image(image_bytes: bytes,
                 output_path: Path,
                 output_format: str = 'jpg',
                 quality: Optional[int] = None,
                 autocontrast: bool = False,
                 cutoff: Optional[int] = None,
                 preserve_tone: bool = False,
                 logger: Optional[Logger] = None) -> None:
    """Process and save image with optional transformations.

    Args:
        image_bytes: Raw image data
        output_path: Path to write output file
        output_format: Output format ('jpg', 'png', 'jp2')
        quality: JPEG quality (1-95)
        autocontrast: Enable autocontrast
        cutoff: Autocontrast cutoff (0-100)
        preserve_tone: Preserve tone in autocontrast
        logger: Optional logger instance
    """
    if logger is None:
        logger = Logger(verbose=False)

    logger.progress("   Processing image...", nl=False)

    # Open image
    img = Image.open(BytesIO(image_bytes))

    # Apply autocontrast if requested or if options were explicitly set
    should_apply_autocontrast = autocontrast or cutoff is not None or preserve_tone
    if should_apply_autocontrast:
        ac_kwargs = {}
        # Use specified cutoff, or default to 2 if autocontrast is enabled but no cutoff specified
        if cutoff is not None:
            ac_kwargs['cutoff'] = cutoff
        else:
            ac_kwargs['cutoff'] = 2
        img = ImageOps.autocontrast(img, **ac_kwargs)

    # Convert format if needed
    save_kwargs = {}
    save_format = output_format.upper()

    if output_format.lower() == 'jpg':
        # Convert RGBA to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background

        if quality:
            save_kwargs['quality'] = quality

        save_format = 'JPEG'

    # Save output
    img.save(output_path, format=save_format, **save_kwargs)
    logger.progress_done("✓")


def download_and_convert_page(ia_id: str,
                             page_num: int,
                             output_path: Path,
                             size: Literal['small', 'medium', 'large', 'original'] = 'medium',
                             output_format: str = 'jpg',
                             quality: Optional[int] = None,
                             autocontrast: bool = False,
                             cutoff: Optional[int] = None,
                             preserve_tone: bool = False,
                             server: Optional[str] = None,
                             logger: Optional[Logger] = None) -> None:
    """High-level function to download and convert a page image.

    Args:
        ia_id: Internet Archive identifier
        page_num: Sequential page number
        output_path: Path to write output file
        size: Image size (small, medium, large, original)
        output_format: Output format (jpg, png, jp2)
        quality: JPEG quality (1-95)
        autocontrast: Enable autocontrast
        cutoff: Autocontrast cutoff (0-100)
        preserve_tone: Preserve tone in autocontrast
        server: Optional server hostname for faster downloads
        logger: Optional logger instance

    Raises:
        ValueError: If size is invalid
        Exception: If download fails
    """
    if logger is None:
        logger = Logger(verbose=False)

    # Validate size parameter
    if size not in ('small', 'medium', 'large', 'original'):
        raise ValueError(f"Invalid size: {size}")

    # Choose image source based on size
    if size == 'original':
        source = JP2ImageSource()
    else:
        source = APIImageSource(size=size)  # type: ignore

    # Download image
    logger.progress(f"   Downloading {size} image...", nl=False)
    try:
        image_bytes = source.fetch(ia_id, page_num)
        size_mb = len(image_bytes) / 1024 / 1024
        logger.progress_done(f"✓ ({size_mb:.1f} MB)")
    except Exception as e:
        logger.progress_fail("✗")
        logger.error(f"Failed to download image: {e}")
        raise

    # Process and save
    process_image(
        image_bytes,
        output_path,
        output_format=output_format,
        quality=quality,
        autocontrast=autocontrast,
        cutoff=cutoff,
        preserve_tone=preserve_tone,
        logger=logger
    )

    logger.info(f"   Saved: {output_path.name}")
