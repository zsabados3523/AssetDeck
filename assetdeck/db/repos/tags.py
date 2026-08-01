"""Tags hierárquicas, aliases PT/EN e atribuição a assets."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- CRUD de tags ----

def create(conn: sqlite3.Connection, name: str, parent_id: int | None = None,
           color: str | None = None) -> int:
    """Cria a tag; se já existir (mesmo nome no mesmo pai), devolve a existente."""
    name = name.strip()
    if not name:
        raise ValueError("Nome de tag não pode ser vazio.")
    row = conn.execute(
        "SELECT id FROM tags WHERE name = ? AND parent_id IS ? AND deleted_at IS NULL",
        (name, parent_id),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO tags (name, parent_id, color) VALUES (?, ?, ?)",
        (name, parent_id, color),
    )
    conn.commit()
    log.info("Tag criada: %r (pai=%s)", name, parent_id)
    return cur.lastrowid


def rename(conn: sqlite3.Connection, tag_id: int, name: str) -> None:
    conn.execute("UPDATE tags SET name = ?, updated_at = ? WHERE id = ?",
                 (name.strip(), _now(), tag_id))
    conn.commit()


def set_color(conn: sqlite3.Connection, tag_id: int, color: str | None) -> None:
    conn.execute("UPDATE tags SET color = ?, updated_at = ? WHERE id = ?",
                 (color, _now(), tag_id))
    conn.commit()


def soft_delete(conn: sqlite3.Connection, tag_id: int) -> int:
    """Soft delete da tag E de todas as subtags. Retorna quantas caíram."""
    alvo = descendants(conn, tag_id)
    marks = ",".join("?" * len(alvo))
    conn.execute(
        f"UPDATE tags SET deleted_at = ?, updated_at = ? WHERE id IN ({marks})",
        [_now(), _now(), *alvo],
    )
    conn.commit()
    log.info("Tag %d soft-deletada (com %d descendentes).", tag_id, len(alvo) - 1)
    return len(alvo)


def list_tree(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Todas as tags ativas, ordenadas para montar a árvore."""
    return conn.execute(
        """SELECT id, parent_id, name, color, sort_order FROM tags
           WHERE deleted_at IS NULL
           ORDER BY parent_id IS NOT NULL, parent_id, sort_order, name COLLATE NOCASE"""
    ).fetchall()


def descendants(conn: sqlite3.Connection, tag_id: int) -> list[int]:
    """Ids da tag + toda a subárvore (para filtrar 'Madeira' incluir 'Nogueira')."""
    filhos: dict[int | None, list[int]] = {}
    for r in conn.execute("SELECT id, parent_id FROM tags WHERE deleted_at IS NULL"):
        filhos.setdefault(r["parent_id"], []).append(r["id"])
    resultado, fila = [], [tag_id]
    while fila:
        atual = fila.pop()
        resultado.append(atual)
        fila.extend(filhos.get(atual, []))
    return resultado


def tag_path(conn: sqlite3.Connection, tag_id: int) -> str:
    """'Materiais/Madeira/Nogueira' — usado no sidecar e na UI."""
    partes: list[str] = []
    atual: int | None = tag_id
    while atual is not None:
        row = conn.execute(
            "SELECT name, parent_id FROM tags WHERE id = ?", (atual,)
        ).fetchone()
        if row is None:
            break
        partes.append(row["name"])
        atual = row["parent_id"]
    return "/".join(reversed(partes))


def get_or_create_path(conn: sqlite3.Connection, path: str) -> int | None:
    """'Materiais/Madeira' → id da folha, criando o caminho se preciso.
    (É como o sidecar restaura tags num banco renascido.)"""
    parent: int | None = None
    tag_id: int | None = None
    for parte in [p.strip() for p in path.split("/") if p.strip()]:
        tag_id = create(conn, parte, parent_id=parent)
        parent = tag_id
    return tag_id


# ---- aliases (sinônimos / bilíngue) ----

def add_alias(conn: sqlite3.Connection, tag_id: int, alias: str,
              lang: str | None = None) -> int:
    cur = conn.execute(
        "INSERT OR IGNORE INTO tag_aliases (tag_id, alias, lang) VALUES (?, ?, ?)",
        (tag_id, alias.strip(), lang),
    )
    conn.commit()
    return cur.lastrowid


def remove_alias(conn: sqlite3.Connection, alias_id: int) -> None:
    conn.execute("DELETE FROM tag_aliases WHERE id = ?", (alias_id,))
    conn.commit()  # alias é metadado de busca, não histórico — pode sair de verdade


def aliases_of(conn: sqlite3.Connection, tag_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, alias, lang FROM tag_aliases WHERE tag_id = ? ORDER BY alias",
        (tag_id,),
    ).fetchall()


# ---- atribuição a assets ----

def assign(conn: sqlite3.Connection, asset_id: int, tag_id: int,
           source: str = "manual", confidence: float | None = None) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, source, confidence)
           VALUES (?, ?, ?, ?)""",
        (asset_id, tag_id, source, confidence),
    )
    conn.commit()


def unassign(conn: sqlite3.Connection, asset_id: int, tag_id: int) -> None:
    conn.execute(
        "DELETE FROM asset_tags WHERE asset_id = ? AND tag_id = ?",
        (asset_id, tag_id),
    )
    conn.commit()


def tags_of(conn: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT t.id, t.name, t.parent_id, t.color, at.source, at.confidence
           FROM asset_tags at JOIN tags t ON t.id = at.tag_id
           WHERE at.asset_id = ? AND t.deleted_at IS NULL
           ORDER BY t.name COLLATE NOCASE""",
        (asset_id,),
    ).fetchall()


def set_tags(conn: sqlite3.Connection, asset_id: int, tag_ids: list[int],
             replace: bool = False) -> None:
    """Aplica um conjunto de tags. replace=True descarta as atuais antes
    (o 'substituir tags' do colar por cima)."""
    if replace:
        conn.execute("DELETE FROM asset_tags WHERE asset_id = ?", (asset_id,))
    for tid in tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, source) "
            "VALUES (?, ?, 'manual')",
            (asset_id, tid),
        )
    conn.commit()
