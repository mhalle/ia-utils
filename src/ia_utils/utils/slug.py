"""Slug generation utilities."""

from typing import List, Tuple
import re


def generate_slug(metadata: List[Tuple[str, str]], ia_id: str) -> str:
    """Generate a human-readable slug from metadata.

    Format: author-title-date-edition_ia_id
    - First author name (last name)
    - First 4 significant words from title (noise words removed)
    - Publication year
    - Edition info (if present)
    - IA ID as unique identifier

    Args:
        metadata: Document metadata as list of (key, value) tuples
        ia_id: Internet Archive identifier

    Returns:
        Human-readable slug
    """
    def get_first(key: str, default: str = '') -> str:
        """Get first value for a key from metadata tuples."""
        for k, v in metadata:
            if k == key:
                return v
        return default

    # Extract first author
    creator = get_first('creator', 'unknown')
    # Handle "Last Name, First Name" format - take first author, last name only
    first_creator = creator.split(';')[0].split(',')[0].strip().lower()
    author = re.sub(r'[^a-z0-9]', '', first_creator)

    # Extract and clean title - keep first 4 significant words
    title = get_first('title', 'document').lower()
    noise_words = {'the', 'of', 'a', 'an', 'and', 'or', 'in', 'for', 'to', 'with', 'by', 'on', 'at'}

    # Remove punctuation and split
    title_cleaned = re.sub(r'[^a-z0-9\s]', '', title)
    words = [w for w in title_cleaned.split() if w and w not in noise_words]
    title_part = '-'.join(words[:4])  # First 4 significant words

    # Extract publication year
    date = get_first('date', '')
    year = date[:4] if date and len(date) >= 4 else ''

    # Check for edition
    edition = get_first('edition', '')
    if edition:
        edition = re.sub(r'[^a-z0-9]', '', edition.lower())

    # Combine parts
    slug_parts = [author, title_part, year]
    if edition:
        slug_parts.append(edition)

    human_readable = '-'.join(p for p in slug_parts if p)
    slug = f"{human_readable}_{ia_id}"

    return slug
