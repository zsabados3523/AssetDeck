"""Coleções manuais: listas de assets organizadas à mão, com subpastas."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- CRUD de coleções ----

def create(conn: sqlite3.Connection, name: str, parent_id: int | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Nome de coleção não pode ser vazio.")
    cur = conn.execute(
        "INSERT INTO collections (name, parent_id) VALUES (?, ?)",
        (name, parent_id),
    )
    conn.commit()
    log.info("Coleção criada: %r (pai=%s)", name, parent_id)
    return cur.lastrowid


def rename(conn: sqlite3.Connection, collection_id: int, name: str) -> None:
    conn.execute("UPDATE collections SET name = ?, updated_at = ? WHERE id = ?",
                 (name.strip(), _now(), collection_id))
    conn.commit()


def soft_delete(conn: sqlite3.Connection, collection_id: int) -> int:
    """Soft delete da coleção E de todas as subcoleções. Retorna quantas caíram."""
    alvo = descendants(conn, collection_id)
    marks = ",".join("?" * len(alvo))
    conn.execute(
        f"UPDATE collections SET deleted_at = ?, updated_at = ? WHERE id IN ({marks})",
        [_now(), _now(), *alvo],
    )
    conn.commit()
    log.info("Coleção %d soft-deletada (com %d descendentes).",
              collection_id, len(alvo) - 1)
    return len(alvo)


def list_tree(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Todas as coleções ativas, ordenadas para montar a árvore."""
    return conn.execute(
        """SELECT id, parent_id, name, sort_order FROM collections
           WHERE deleted_at IS NULL
           ORDER BY parent_id IS NOT NULL, parent_id, sort_order, name COLLATE NOCASE"""
    ).fetchall()


def descendants(conn: sqlite3.Connection, collection_id: int) -> list[int]:
    """Ids da coleção + toda a subárvore (para soft delete em cascata)."""
    filhos: dict[int | None, list[int]] = {}
    for r in conn.execute("SELECT id, parent_id FROM collections WHERE deleted_at IS NULL"):
        filhos.setdefault(r["parent_id"], []).append(r["id"])
    resultado, fila = [], [collection_id]
    while fila:
        atual = fila.pop()
        resultado.append(atual)
        fila.extend(filhos.get(atual, []))
    return resultado


# ---- itens da coleção ----

def add_items(conn: sqlite3.Connection, collection_id: int, asset_ids: list[int]) -> int:
    """Acrescenta assets ao FIM da coleção (ordem manual = ordem de chegada).
    Ids já presentes não duplicam nem mudam de posição. Retorna quantos entraram."""
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) AS o FROM collection_items"
        " WHERE collection_id = ?",
        (collection_id,),
    ).fetchone()
    proximo = row["o"] + 1
    adicionados = 0
    for aid in asset_ids:
        cur = conn.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, asset_id, sort_order)"
            " VALUES (?, ?, ?)",
            (collection_id, aid, proximo),
        )
        if cur.rowcount:
            proximo += 1
            adicionados += 1
    conn.commit()
    return adicionados


def remove_item(conn: sqlite3.Connection, collection_id: int, asset_id: int) -> None:
    conn.execute(
        "DELETE FROM collection_items WHERE collection_id = ? AND asset_id = ?",
        (collection_id, asset_id),
    )
    conn.commit()
