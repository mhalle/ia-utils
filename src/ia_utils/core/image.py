"""Image processing and fetching for page images."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Literal
from io import BytesIO
import httpx
from PIL import Image, ImageOps, ImageDraw, ImageFont

from ia_utils.utils.logger import Logger


def get_api_image_url(ia_id: str, leaf_num: int, size: str = 'medium') -> str:
    """Get URL for a page image from the IA API.

    Args:
        ia_id: Internet Archive identifier
        leaf_num: Leaf number (physical scan order)
        size: Image size (small, medium, large)

    Returns:
        URL string
    """
    return f"https://archive.org/download/{ia_id}/page/leaf{leaf_num}_{size}.jpg"


def get_server_from_metadata(ia_id: str) -> str:
    """Get the actual IA server hosting an item from metadata API.

    Args:
        ia_id: Internet Archive identifier

    Returns:
        Server hostname (e.g., 'ia800508.us.archive.org') or 'archive.org' as fallback
    """
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(f'https://archive.org/metadata/{ia_id}')
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
    def fetch(self, ia_id: str, leaf_num: int) -> bytes:
        """Fetch raw image bytes for a page by leaf number."""
        pass


class APIImageSource(ImageSource):
    """Fetch images from Internet Archive API (small, medium, large)."""

    def __init__(self, size: Literal['small', 'medium', 'large'] = 'medium'):
        if size not in ('small', 'medium', 'large'):
            raise ValueError(f"Invalid API size: {size}")
        self.size = size

    def fetch(self, ia_id: str, leaf_num: int) -> bytes:
        """Fetch image from IA page API.

        Args:
            ia_id: Internet Archive identifier
            leaf_num: Leaf number (physical scan order)

        Returns:
            Image bytes

        Raises:
            Exception: If download fails
        """
        url = get_api_image_url(ia_id, leaf_num, self.size)
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content


class JP2ImageSource(ImageSource):
    """Fetch images from jp2.zip using direct URL (original quality).

    Uses Internet Archive's ZIP-as-directory URL format which allows
    direct access to individual files within a ZIP archive without
    downloading the entire archive.
    """

    def fetch(self, ia_id: str, leaf_num: int) -> bytes:
        """Fetch image from JP2 archive using direct URL.

        Args:
            ia_id: Internet Archive identifier
            leaf_num: Leaf number (physical scan order, maps directly to JP2 files)

        Returns:
            Image bytes

        Raises:
            Exception: If download fails
        """
        # JP2 files use leaf numbering: leaf N = _{N:04d}.jp2
        jp2_page_num = f"{leaf_num:04d}"
        jp2_filename = f"{ia_id}_{jp2_page_num}.jp2"

        # Use IA's ZIP-as-directory URL format for direct file access
        # Format: https://archive.org/download/{id}/{id}_jp2.zip/{id}_jp2/{id}_{leaf:04d}.jp2
        url = f"https://archive.org/download/{ia_id}/{ia_id}_jp2.zip/{ia_id}_jp2/{jp2_filename}"

        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise FileNotFoundError(f"Leaf {leaf_num} ({jp2_filename}) not found in archive")
            raise Exception(f"Failed to fetch JP2 for leaf {leaf_num}: {e}")
        except Exception as e:
            raise Exception(f"Failed to fetch JP2 for leaf {leaf_num}: {e}")


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

    # Check if any transformations are requested
    needs_processing = autocontrast or cutoff is not None or preserve_tone

    # For JP2 output with no processing, just write raw bytes
    # (PIL cannot write JP2 format)
    if output_format.lower() == 'jp2' and not needs_processing:
        logger.progress("   Saving JP2...", nl=False)
        output_path.write_bytes(image_bytes)
        logger.progress_done("✓")
        return

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
                             leaf_num: int,
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
        leaf_num: Leaf number (physical scan order)
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
        image_bytes = source.fetch(ia_id, leaf_num)
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

    logger.verbose_info(f"   Saved: {output_path.name}")


def create_mosaic(
    images: list[bytes],
    labels: Optional[list[str]] = None,
    width: int = 1536,
    cols: int = 12,
    grid: bool = False,
) -> Image.Image:
    """Create a mosaic grid from page images.

    Args:
        images: List of image bytes
        labels: Optional list of label strings (same length as images)
        width: Output image width in pixels
        cols: Number of columns
        grid: Whether to draw grid lines between tiles

    Returns:
        PIL Image object
    """
    if not images:
        raise ValueError("No images provided")

    # Calculate tile dimensions
    tile_width = width // cols

    # Open all images and resize to tile width (maintain aspect ratio)
    tiles = []
    tile_height = None  # Will be determined from first image's aspect ratio

    for img_bytes in images:
        img = Image.open(BytesIO(img_bytes))

        # Calculate height maintaining aspect ratio
        aspect = img.height / img.width
        new_height = int(tile_width * aspect)

        # Use first image to set tile_height for all
        if tile_height is None:
            tile_height = new_height

        # Resize image
        img = img.resize((tile_width, tile_height), Image.Resampling.LANCZOS)

        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')

        tiles.append(img)

    # Calculate canvas size
    rows = (len(tiles) + cols - 1) // cols  # Ceiling division
    canvas_width = cols * tile_width
    canvas_height = rows * tile_height

    # Create canvas
    canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))

    # Paste tiles
    for idx, tile in enumerate(tiles):
        row = idx // cols
        col = idx % cols
        x = col * tile_width
        y = row * tile_height
        canvas.paste(tile, (x, y))

    # Draw labels if provided
    if labels:
        draw = ImageDraw.Draw(canvas)

        # Try to get a font - use default with size if available (PIL 10+)
        try:
            font = ImageFont.load_default(size=18)
        except TypeError:
            # Fallback for older PIL versions
            font = ImageFont.load_default()

        for idx, label in enumerate(labels):
            if not label:
                continue

            row = idx // cols
            col = idx % cols

            # Calculate tile position
            tile_x = col * tile_width
            tile_y = row * tile_height

            # Get text size
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Position in SE corner with padding from edge
            edge_padding = 6
            bg_padding = 5

            # Calculate background rectangle position first
            bg_right = tile_x + tile_width - edge_padding
            bg_bottom = tile_y + tile_height - edge_padding
            bg_left = bg_right - text_width - (bg_padding * 2)
            bg_top = bg_bottom - text_height - (bg_padding * 2)

            # Draw white background rectangle
            draw.rectangle([bg_left, bg_top, bg_right, bg_bottom], fill='white')

            # Draw text centered in the background
            label_x = bg_left + bg_padding
            label_y = bg_top + bg_padding
            draw.text((label_x, label_y), label, fill='black', font=font)

    # Draw grid lines if requested
    if grid:
        draw = ImageDraw.Draw(canvas)
        grid_color = (128, 128, 128)  # Gray

        # Vertical lines
        for col in range(1, cols):
            x = col * tile_width
            draw.line([(x, 0), (x, canvas_height)], fill=grid_color, width=1)

        # Horizontal lines
        for row in range(1, rows):
            y = row * tile_height
            draw.line([(0, y), (canvas_width, y)], fill=grid_color, width=1)

    return canvas
