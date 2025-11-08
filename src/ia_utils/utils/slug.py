"""Slug generation utilities."""

from typing import Dict, Any
import re


def generate_slug(metadata: Dict[str, Any], ia_id: str) -> str:
    """Generate a human-readable slug from metadata.

    Format: author-title-date-edition_ia_id
    - First author name (last name)
    - First 4 significant words from title (noise words removed)
    - Publication year
    - Edition info (if present)
    - IA ID as unique identifier

    Args:
        metadata: Document metadata dictionary
        ia_id: Internet Archive identifier

    Returns:
        Human-readable slug
    """
    # Extract first author
    creators = metadata.get('creator', 'unknown')
    if isinstance(creators, str):
        # Handle "Last Name, First Name" format - take first author, last name only
        first_creator = creators.split(';')[0].split(',')[0].strip().lower()
        author = re.sub(r'[^a-z0-9]', '', first_creator)
    else:
        author = 'unknown'

    # Extract and clean title - keep first 4 significant words
    title = metadata.get('title', 'document').lower()
    noise_words = {'the', 'of', 'a', 'an', 'and', 'or', 'in', 'for', 'to', 'with', 'by', 'on', 'at'}

    # Remove punctuation and split
    title_cleaned = re.sub(r'[^a-z0-9\s]', '', title)
    words = [w for w in title_cleaned.split() if w and w not in noise_words]
    title_part = '-'.join(words[:4])  # First 4 significant words

    # Extract publication year
    date = metadata.get('date', '')
    year = date[:4] if date and len(date) >= 4 else ''

    # Check for edition
    edition = metadata.get('edition', '')
    if edition:
        edition = re.sub(r'[^a-z0-9]', '', edition.lower())

    # Combine parts
    slug_parts = [author, title_part, year]
    if edition:
        slug_parts.append(edition)

    human_readable = '-'.join(p for p in slug_parts if p)
    slug = f"{human_readable}_{ia_id}"

    return slug
