"""Rebuild catalog command."""

import click


@click.command()
@click.argument('catalog', type=click.Path(exists=True))
def rebuild_catalog(catalog):
    """Rebuild text_blocks and FTS indexes in an existing catalog database."""
    # TODO: Implement rebuild_catalog command
    pass
