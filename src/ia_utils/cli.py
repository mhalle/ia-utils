"""Main CLI entry point for ia-utils."""

import click

from ia_utils import __version__
from ia_utils.commands.create_index import create_index
from ia_utils.commands.info import info
from ia_utils.commands.get_page import get_page
from ia_utils.commands.get_pages import get_pages
from ia_utils.commands.get_page_stats import get_page_stats
from ia_utils.commands.get_pdf import get_pdf
from ia_utils.commands.get_text import get_text
from ia_utils.commands.get_url import get_url
from ia_utils.commands.list_files import list_files
from ia_utils.commands.ocr_page import ocr_page
from ia_utils.commands.search_index import search_index
from ia_utils.commands.search_ia import search_ia
from ia_utils.commands.rebuild_index import rebuild_index


@click.group()
@click.version_option(version=__version__, prog_name='ia-utils')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Tools for working with Internet Archive books and documents.

    TYPICAL WORKFLOW:

    \b
    1. DISCOVER: Search Internet Archive for books/documents
       ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts
    2. CREATE INDEX: Build searchable database from a document
       ia-utils create-index <ia_id> -d ./indexes/
    3. SEARCH INDEX: Find pages by OCR text content
       ia-utils search-index -i index.sqlite -q "femur"
    4. DOWNLOAD: Get pages, PDFs, or URLs
       ia-utils get-page -i index.sqlite -l 42
       ia-utils get-pdf -i index.sqlite
       ia-utils get-url -i index.sqlite -l 42 --viewer

    COMMAND GROUPS:

    \b
    Discovery:
      search-ia        Search IA metadata (by title, creator, year, etc.)
      info             Show metadata about index or IA item
      list-files       List files in an IA item with download URLs
    Index Management:
      create-index     Build index database from IA document
      rebuild-index    Rebuild index's text/FTS indexes
      search-index     Search index by OCR text content
    Downloading:
      get-page         Download single page image
      get-pages        Download page images (range, --all, --zip)
      get-pdf          Download PDF
      get-text         Get OCR text from index
      get-url          Get URL without downloading
      ocr-page         Run local OCR on a page (pytesseract)

    IDENTIFIERS:

    \b
    Most commands accept IA identifiers in multiple forms:
      - ID: anatomicalatlasi00smit
      - URL: https://archive.org/details/anatomicalatlasi00smit
      - Index: -i index.sqlite (reads ID from database)

    Use -v/--verbose for detailed progress output.
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


# Register commands
cli.add_command(create_index)
cli.add_command(get_page)
cli.add_command(get_pages)
cli.add_command(get_page_stats)
cli.add_command(get_pdf)
cli.add_command(get_text)
cli.add_command(get_url)
cli.add_command(info)
cli.add_command(list_files)
cli.add_command(ocr_page)
cli.add_command(rebuild_index)
cli.add_command(search_index)
cli.add_command(search_ia)


if __name__ == '__main__':
    cli()
