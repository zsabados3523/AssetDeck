"""Queries de assets. A UI nunca escreve SQL — sempre passa por aqui."""

from __future__ import annotations

import sqlite3


def count_active(conn: sqlite3.Connection) -> int:
    """Quantos assets existem (soft-deleted não contam)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE deleted_at IS NULL"
    ).fetchone()
    return row["n"]


def list_for_grid(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Tudo que a grid precisa: asset + arquivo principal, em ordem de nome."""
    return conn.execute(
        """SELECT a.id, a.name, a.asset_type,
                  f.rel_path, f.size_bytes, f.content_hash, f.missing_since
           FROM assets a
           JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
           WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL
           ORDER BY a.name COLLATE NOCASE""",
    ).fetchall()
