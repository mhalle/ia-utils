"""`ia-utils outline-status` — show outline-population status across indices."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import click

from ia_utils.utils.output import write_output

FORMATS = ("table", "records", "json", "jsonl", "csv")

STATUS_FIELDS = [
    "file",
    "work_id",
    "canvases",
    "outline_rows",
    "top_level",
    "max_depth",
]


@click.command(name="outline-status")
@click.argument(
    "index_paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(FORMATS),
    default="table",
    help="Output format (default table).",
)
@click.option(
    "--missing-only",
    is_flag=True,
    default=False,
    help="Only show indices that have no outline yet.",
)
def outline_status(
    index_paths: tuple[Path, ...], fmt: str, missing_only: bool
) -> None:
    """Show outline-population status across one or more sqlite indices.

    One row per index, with canvas count, outline row count (or "—" when
    absent), top-level row count, max nesting depth, and the work id.
    Useful for tracking progress across a corpus when populating outlines
    in batch.

    Pass multiple paths or a shell glob:

        ia-utils outline-status indexes/*.sqlite
    """
    rows: list[dict[str, Any]] = [_status_for(p) for p in index_paths]

    if missing_only:
        rows = [r for r in rows if r["outline_rows"] == 0]

    if not rows:
        click.echo("(no rows)", err=True)
        return

    if fmt == "table":
        _print_table(rows)
        return

    write_output(fmt, STATUS_FIELDS, rows)


def _status_for(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        max_canvas = 0
        if "page_numbers" in tables:
            row = conn.execute("SELECT MAX(leaf_num) FROM page_numbers").fetchone()
            if row and row[0] is not None:
                max_canvas = row[0] + 1

        work_id: str = path.stem
        if "document_metadata" in tables:
            cols = {
                r[1] for r in conn.execute("PRAGMA table_info(document_metadata)")
            }
            if {"key", "value"}.issubset(cols):
                r = conn.execute(
                    "SELECT value FROM document_metadata WHERE key='identifier'"
                ).fetchone()
                if r and r[0]:
                    work_id = r[0]
            elif "ia_identifier" in cols:
                r = conn.execute(
                    "SELECT ia_identifier FROM document_metadata LIMIT 1"
                ).fetchone()
                if r and r[0]:
                    work_id = r[0]

        outline_rows = 0
        top_level = 0
        max_depth = 0
        if "derived_outline" in tables:
            outline_rows = conn.execute(
                "SELECT COUNT(*) FROM derived_outline"
            ).fetchone()[0]
            top_level = conn.execute(
                "SELECT COUNT(*) FROM derived_outline WHERE parent_id IS NULL"
            ).fetchone()[0]
            md = conn.execute("SELECT MAX(level) FROM derived_outline").fetchone()
            if md and md[0] is not None:
                max_depth = md[0]

        return {
            "file": path.name,
            "work_id": work_id,
            "canvases": max_canvas,
            "outline_rows": outline_rows,
            "top_level": top_level,
            "max_depth": max_depth,
        }
    finally:
        conn.close()


def _print_table(rows: list[dict[str, Any]]) -> None:
    """Aligned table — shows '—' for unpopulated outlines."""
    name_w = max(len(r["file"]) for r in rows)
    work_w = max(len(str(r["work_id"])) for r in rows) or 1
    header = (
        f"{'file':<{name_w}}  {'work':<{work_w}}  "
        f"{'canv':>5}  {'outl':>5}  {'top':>4}  {'depth':>5}"
    )
    click.echo(header)
    click.echo("-" * len(header))
    n_populated = 0
    for r in rows:
        outl = str(r["outline_rows"]) if r["outline_rows"] else "—"
        top = str(r["top_level"]) if r["outline_rows"] else "—"
        depth = str(r["max_depth"]) if r["outline_rows"] else "—"
        click.echo(
            f"{r['file']:<{name_w}}  {str(r['work_id']):<{work_w}}  "
            f"{r['canvases']:>5}  {outl:>5}  {top:>4}  {depth:>5}"
        )
        if r["outline_rows"]:
            n_populated += 1
    click.echo("-" * len(header))
    click.echo(
        f"{n_populated} / {len(rows)} indices have an outline.",
        err=True,
    )
