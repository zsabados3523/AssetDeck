"""Smart Collections: buscas salvas como query JSON, recalculadas na hora.

Diferente de `collections.py`: não guarda assets, guarda o dicionário de
filtros que `assets_repo.list_for_grid` já aceita. O resultado nunca fica
"congelado" — é a mesma consulta rodando de novo contra o banco atual.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(conn: sqlite3.Connection, name: str, query: dict) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Nome da coleção inteligente não pode ser vazio.")
    cur = conn.execute(
        "INSERT INTO smart_collections (name, query_json) VALUES (?, ?)",
        (name, json.dumps(query)),
    )
    conn.commit()
    log.info("Smart collection criada: %r", name)
    return cur.lastrowid


def rename(conn: sqlite3.Connection, smart_id: int, name: str) -> None:
    conn.execute("UPDATE smart_collections SET name = ?, updated_at = ? WHERE id = ?",
                 (name.strip(), _now(), smart_id))
    conn.commit()


def soft_delete(conn: sqlite3.Connection, smart_id: int) -> None:
    conn.execute("UPDATE smart_collections SET deleted_at = ?, updated_at = ? WHERE id = ?",
                 (_now(), _now(), smart_id))
    conn.commit()
    log.info("Smart collection %d soft-deletada.", smart_id)


def list_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT id, name, query_json FROM smart_collections
           WHERE deleted_at IS NULL ORDER BY sort_order, name COLLATE NOCASE"""
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "query": json.loads(r["query_json"])}
            for r in rows]


def get(conn: sqlite3.Connection, smart_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, name, query_json FROM smart_collections"
        " WHERE id = ? AND deleted_at IS NULL",
        (smart_id,),
    ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "query": json.loads(row["query_json"])}
