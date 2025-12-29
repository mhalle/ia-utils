"""
CLI tool to work with Internet Archive documents.

Utilities for building searchable SQLite catalog databases from any IA document
(textbooks, manuscripts, journals, atlases, etc.) that has OCR (hOCR HTML format),
and downloading/converting page images.
"""

from importlib.metadata import version
__version__ = version("ia-utils")
