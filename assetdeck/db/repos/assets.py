"""Queries de assets. A UI nunca escreve SQL — sempre passa por aqui."""

from __future__ import annotations

import sqlite3


def count_active(conn: sqlite3.Connection) -> int:
    """Quantos assets existem (soft-deleted não contam)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE deleted_at IS NULL"
    ).fetchone()
    return row["n"]
