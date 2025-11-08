"""Image processing and fetching for page images."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Literal
from io import BytesIO
from PIL import Image, ImageOps


class ImageSource(ABC):
    """Abstract base class for image sources."""

    @abstractmethod
    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch raw image bytes for a page."""
        pass


class APIImageSource(ImageSource):
    """Fetch images from Internet Archive API (small, medium, large)."""

    def __init__(self, size: Literal['small', 'medium', 'large'] = 'medium'):
        self.size = size

    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch image from IA API."""
        # TODO: Implement API image fetching
        pass


class JP2ImageSource(ImageSource):
    """Fetch images from jp2.zip using remotezip (original quality)."""

    def fetch(self, ia_id: str, page_num: int) -> bytes:
        """Fetch image from JP2 archive."""
        # TODO: Implement JP2 image fetching
        pass


def process_image(image_bytes: bytes,
                 output_path: Path,
                 output_format: str = 'jpg',
                 width: Optional[int] = None,
                 quality: Optional[int] = None,
                 autocontrast: bool = False,
                 cutoff: Optional[int] = None,
                 preserve_tone: bool = False) -> None:
    """Process and save image with optional transformations."""
    # TODO: Implement image processing
    pass


def download_and_convert_page(ia_id: str,
                             page_num: int,
                             output_path: Path,
                             size: Literal['small', 'medium', 'large', 'original'] = 'medium',
                             output_format: str = 'jpg',
                             quality: Optional[int] = None,
                             autocontrast: bool = False,
                             cutoff: Optional[int] = None,
                             preserve_tone: bool = False,
                             verbose: bool = False) -> None:
    """High-level function to download and convert a page image."""
    # TODO: Implement download_and_convert_page
    pass
