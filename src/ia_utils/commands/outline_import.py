"""`ia-utils outline-import` — bulk-load a derived navigation outline."""
from __future__ import annotations

import json
from pathlib import Path

import click
import sqlite_utils

from ia_utils.core import outline as outline_mod
from ia_utils.utils.logger import Logger


@click.command(name="outline-import")
@click.argument("index_path", type=click.Path(exists=True, path_type=Path))
@click.argument("payload_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--replace",
    is_flag=True,
    default=False,
    help="Clear existing derived_outline rows before importing.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate the payload without writing to the db.",
)
@click.pass_context
def outline_import(
    ctx: click.Context,
    index_path: Path,
    payload_path: Path,
    replace: bool,
    dry_run: bool,
) -> None:
    """Bulk-load a derived navigation outline into an index database.

    The payload is a JSON document. See docs/outline.md for the schema.
    The schema matches iiif-utils' `derived_outline` exactly, so payloads
    are interchangeable between the two CLIs.

    Atomic: validation errors or insertion failures roll back the
    transaction. Refuses to import over an existing outline unless
    --replace is given.
    """
    verbose = bool(ctx.obj.get("verbose")) if ctx.obj else False
    log = Logger(verbose=verbose)

    try:
        payload = json.loads(payload_path.read_text())
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{payload_path}: invalid JSON — {exc}") from exc

    db = sqlite_utils.Database(index_path)

    work = outline_mod.work_id(db, db_path=index_path)
    if not work:
        raise click.ClickException(
            f"{index_path}: no work id (document_metadata 'identifier' missing "
            f"and filename has no stem) — is this a real ia-utils index?"
        )

    errors = outline_mod.validate_payload(
        payload,
        expected_work=work,
        max_canvas_idx=outline_mod.max_canvas(db),
    )
    if errors:
        msg = "validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise click.ClickException(msg)

    total = outline_mod.count_entries(payload["entries"])

    if dry_run:
        click.echo(f"OK (dry-run): {total} entries valid for {work}")
        return

    outline_mod.ensure_table(db)

    existing = db.execute(
        f"SELECT COUNT(*) FROM {outline_mod.OUTLINE_TABLE}"
    ).fetchone()[0]
    if existing and not replace:
        raise click.ClickException(
            f"{outline_mod.OUTLINE_TABLE} already has {existing} rows. "
            f"Pass --replace to overwrite."
        )

    with db.conn:
        if existing and replace:
            db.execute(f"DELETE FROM {outline_mod.OUTLINE_TABLE}")
            log.verbose_info(f"cleared {existing} existing rows")
        n = outline_mod.insert_tree(db, payload["entries"])

    click.echo(f"imported {n} outline entries into {index_path}")
