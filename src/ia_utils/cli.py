"""Main CLI entry point for ia-utils."""

import click

from ia_utils.commands.catalog_info import catalog_info
from ia_utils.commands.create_catalog import create_catalog
from ia_utils.commands.get_page import get_page
from ia_utils.commands.get_pages import get_pages
from ia_utils.commands.get_pdf import get_pdf
from ia_utils.commands.get_text import get_text
from ia_utils.commands.get_url import get_url
from ia_utils.commands.search_catalog import search_catalog
from ia_utils.commands.search_ia import search_ia
from ia_utils.commands.rebuild_catalog import rebuild_catalog


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Tools for working with Internet Archive books and documents.

    TYPICAL WORKFLOW:

    \b
    1. DISCOVER: Search Internet Archive for books/documents
       ia-utils search-ia -q "anatomy atlas" --year 1900-1940 -m texts
    2. CREATE CATALOG: Build searchable database from a document
       ia-utils create-catalog <ia_id> -d ./catalogs/
    3. SEARCH CATALOG: Find pages by OCR text content
       ia-utils search-catalog -c catalog.sqlite -q "femur"
    4. DOWNLOAD: Get pages, PDFs, or URLs
       ia-utils get-page -c catalog.sqlite -l 42
       ia-utils get-pdf -c catalog.sqlite

    COMMAND GROUPS:

    \b
    Discovery:
      search-ia        Search IA metadata (by title, creator, year, etc.)
    Catalog Management:
      create-catalog   Build catalog database from IA document
      catalog-info     Show metadata about catalog(s)
      rebuild-catalog  Rebuild catalog's text/FTS indexes
      search-catalog   Search catalog by OCR text content
    Downloading:
      get-page         Download single page image
      get-pages        Download page images (range, --all, --zip)
      get-pdf          Download PDF
      get-text         Get OCR text from catalog
      get-url          Get URL without downloading

    IDENTIFIERS:

    \b
    Most commands accept IA identifiers in multiple forms:
      - ID: anatomicalatlasi00smit
      - URL: https://archive.org/details/anatomicalatlasi00smit
      - Catalog: -c catalog.sqlite (reads ID from database)

    Use -v/--verbose for detailed progress output.
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


# Register commands
cli.add_command(catalog_info)
cli.add_command(create_catalog)
cli.add_command(get_page)
cli.add_command(get_pages)
cli.add_command(get_pdf)
cli.add_command(get_text)
cli.add_command(get_url)
cli.add_command(rebuild_catalog)
cli.add_command(search_catalog)
cli.add_command(search_ia)


if __name__ == '__main__':
    cli()
