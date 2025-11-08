"""Search command."""

import click


@click.command()
@click.argument('catalog', type=click.Path(exists=True))
@click.argument('search_string')
@click.option('--limit', type=int, default=10, help='Maximum results')
@click.option('--type', 'block_type', type=str, help='Filter by block type')
@click.option('--page', type=str, help='Filter by book page number')
def search(catalog, search_string, limit, block_type, page):
    """Search catalog database using FTS on OCR text."""
    # TODO: Implement search command
    pass
