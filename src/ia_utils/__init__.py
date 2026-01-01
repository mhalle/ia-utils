"""
CLI tool to work with Internet Archive documents.

Utilities for building searchable SQLite index databases from any IA document
(textbooks, manuscripts, journals, atlases, etc.) that has OCR (hOCR HTML format),
and downloading/converting page images.
"""

try:
    from ._version import __version__
except ImportError:
    from importlib.metadata import version
    __version__ = version("ia-utils")
