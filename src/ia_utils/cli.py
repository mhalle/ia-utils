"""Main CLI entry point for ia-utils."""

import click

from ia_utils.commands.create_catalog import create_catalog
from ia_utils.commands.get_page import get_page
from ia_utils.commands.get_pages import get_pages
from ia_utils.commands.get_pdf import get_pdf
from ia_utils.commands.get_book_pages import get_book_pages
from ia_utils.commands.get_url import get_url
from ia_utils.commands.search_catalog import search_catalog
from ia_utils.commands.search_ia import search_ia
from ia_utils.commands.rebuild_catalog import rebuild_catalog


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Build and manage Internet Archive document catalogs."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


# Register commands
cli.add_command(create_catalog)
cli.add_command(get_page)
cli.add_command(get_pages)
cli.add_command(get_book_pages)
cli.add_command(get_pdf)
cli.add_command(get_url)
cli.add_command(rebuild_catalog)
cli.add_command(search_catalog)
cli.add_command(search_ia)


if __name__ == '__main__':
    cli()
