"""`derived_outline` — synthesized navigation outline per IA work.

Each row is a self-contained entry: a title plus a leaf range. `parent_id`
links to a parent (for hierarchy) but is not load-bearing for ordering or
boundary computation; rows carry `canvas_start` / `canvas_end` explicitly,
where the canvas index is the `page_numbers.leaf_num` of the IA scan.

The schema is intentionally identical to iiif-utils' `derived_outline` so
the same JSON payload can be imported into either project's sqlite index.
See `docs/outline.md` for the user-facing description and payload format.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import sqlite_utils

from ia_utils.core.database import get_document_metadata

OUTLINE_TABLE = "derived_outline"


def ensure_table(db: sqlite_utils.Database) -> None:
    """Create `derived_outline` if it doesn't exist. Idempotent."""
    if OUTLINE_TABLE in db.table_names():
        return
    db.executescript(
        """
        CREATE TABLE derived_outline (
          id                 INTEGER PRIMARY KEY,
          level              INTEGER NOT NULL,
          parent_id          INTEGER REFERENCES derived_outline(id),
          title              TEXT    NOT NULL,
          printed_page_start TEXT,
          printed_page_end   TEXT,
          canvas_start       INTEGER NOT NULL,
          canvas_end         INTEGER NOT NULL,
          notes              TEXT
        );
        CREATE INDEX ix_outline_canvas ON derived_outline(canvas_start);
        CREATE INDEX ix_outline_parent ON derived_outline(parent_id);
        """
    )


def work_id(db: sqlite_utils.Database, db_path: Path | None = None) -> str | None:
    """Return the canonical work id for an ia-utils index db.

    Prefers the IA `identifier` from `document_metadata` (the authoritative
    archive.org id). Falls back to the sqlite filename stem if metadata is
    missing — matching iiif-utils' convention.
    """
    meta = get_document_metadata(db)
    ident = meta.get("identifier")
    if ident:
        return ident
    if db_path is not None:
        return db_path.stem
    row = db.execute("PRAGMA database_list").fetchone()
    if row and row[2]:
        return Path(cast(str, row[2])).stem
    return None


def max_canvas(db: sqlite_utils.Database) -> int:
    """Return max(leaf_num) from page_numbers, or -1 if absent/empty."""
    if "page_numbers" not in db.table_names():
        return -1
    row = db.execute("SELECT MAX(leaf_num) FROM page_numbers").fetchone()
    return row[0] if row and row[0] is not None else -1


def validate_payload(
    payload: Any, *, expected_work: str, max_canvas_idx: int
) -> list[str]:
    """Return a list of validation error strings. Empty list = payload is OK."""
    errors: list[str] = []

    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]

    work = payload.get("work")
    if work != expected_work:
        errors.append(
            f"payload.work = {work!r} does not match db work id "
            f"= {expected_work!r}"
        )

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("payload.entries must be a non-empty array")
        return errors

    flat_canvas_starts: list[int] = []
    flat_titles: list[str] = []

    def walk(node: Any, depth: int, parent_range: tuple[int, int] | None,
             path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}: entry must be an object (got {type(node).__name__})")
            return

        title = node.get("title")
        if not isinstance(title, str) or not title:
            errors.append(f"{path}: title must be a non-empty string")

        for required in ("level", "canvas_start", "canvas_end"):
            if required not in node:
                errors.append(f"{path} ({title!r}): missing required field {required!r}")

        level = node.get("level")
        if isinstance(level, int) and level != depth:
            errors.append(
                f"{path} ({title!r}): level={level} but nesting depth={depth}"
            )

        cs_raw = node.get("canvas_start")
        ce_raw = node.get("canvas_end")
        valid_range = isinstance(cs_raw, int) and isinstance(ce_raw, int)
        child_range: tuple[int, int] | None = None
        if valid_range:
            cs: int = cs_raw  # type: ignore[assignment]
            ce: int = ce_raw  # type: ignore[assignment]
            if ce < cs:
                errors.append(
                    f"{path} ({title!r}): canvas_end={ce} < canvas_start={cs}"
                )
            if cs < 0 or ce > max_canvas_idx:
                errors.append(
                    f"{path} ({title!r}): canvas range [{cs}, {ce}] "
                    f"outside work extent [0, {max_canvas_idx}]"
                )
            if parent_range is not None:
                ps, pe = parent_range
                if cs < ps or ce > pe:
                    errors.append(
                        f"{path} ({title!r}): child range [{cs}, {ce}] "
                        f"not within parent [{ps}, {pe}]"
                    )
            flat_canvas_starts.append(cs)
            flat_titles.append(str(title) if title else "")
            child_range = (cs, ce)

        for ppk in ("printed_page_start", "printed_page_end"):
            v = node.get(ppk)
            if v is not None and not isinstance(v, (int, str)):
                errors.append(
                    f"{path} ({title!r}): {ppk} must be int, string, or null"
                )
            if isinstance(v, str) and not v.strip():
                errors.append(f"{path} ({title!r}): {ppk} must not be empty string")

        notes = node.get("notes")
        if notes is not None and not isinstance(notes, str):
            errors.append(f"{path} ({title!r}): notes must be string or null")

        children = node.get("children")
        if children is None:
            children = []
        if not isinstance(children, list):
            errors.append(f"{path} ({title!r}): children must be an array")
            return

        for idx, child in enumerate(children):
            walk(child, depth + 1, child_range, f"{path}/children[{idx}]")

    for idx, entry in enumerate(entries):
        walk(entry, 0, None, f"entries[{idx}]")

    for i in range(1, len(flat_canvas_starts)):
        if flat_canvas_starts[i] < flat_canvas_starts[i - 1]:
            errors.append(
                f"flattened canvas_start sequence not monotonic at position {i}: "
                f"entry {flat_titles[i]!r} (canvas_start={flat_canvas_starts[i]}) "
                f"comes after entry {flat_titles[i - 1]!r} "
                f"(canvas_start={flat_canvas_starts[i - 1]})"
            )

    return errors


def count_entries(entries: list[dict[str, Any]]) -> int:
    """Total entries including nested children."""
    n = 0
    for e in entries:
        n += 1
        n += count_entries(e.get("children") or [])
    return n


def insert_tree(
    db: sqlite_utils.Database,
    entries: list[dict[str, Any]],
    parent_id: int | None = None,
) -> int:
    """Insert a tree of entries, returning the row count.

    Walks top-down so that parents are inserted before children and each
    child's `parent_id` references the freshly-assigned parent id.
    """
    n = 0
    for node in entries:
        row = {
            "level": node["level"],
            "parent_id": parent_id,
            "title": node["title"],
            "printed_page_start": node.get("printed_page_start"),
            "printed_page_end": node.get("printed_page_end"),
            "canvas_start": node["canvas_start"],
            "canvas_end": node["canvas_end"],
            "notes": node.get("notes"),
        }
        table = cast(sqlite_utils.db.Table, db[OUTLINE_TABLE])
        result = table.insert(row)
        new_id = cast(int, result.last_pk)
        n += 1
        children = node.get("children") or []
        if children:
            n += insert_tree(db, children, parent_id=new_id)
    return n
