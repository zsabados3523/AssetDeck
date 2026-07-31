"""Queries de bibliotecas (raízes indexadas)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


def get_or_create(conn: sqlite3.Connection, root_path: Path, name: str | None = None) -> int:
    """Devolve o id da library desta raiz, criando a linha se for a primeira vez."""
    root = str(root_path)
    row = conn.execute(
        "SELECT id FROM libraries WHERE root_path = ? AND deleted_at IS NULL", (root,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO libraries (name, root_path) VALUES (?, ?)",
        (name or Path(root).name, root),
    )
    conn.commit()
    log.info("Biblioteca registrada no banco: %s (id=%d)", root, cur.lastrowid)
    return cur.lastrowid
