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
           color: str | None = None, icon: str | None = None) -> int:
    """Cria a tag; se já existir (mesmo nome no mesmo pai), devolve a existente."""
    name = name.strip()
    if not name:
        raise ValueError("Nome de tag não pode ser vazio.")
    row = conn.execute(
        "SELECT id, deleted_at FROM tags WHERE name = ? AND parent_id IS ?",
        (name, parent_id),
    ).fetchone()
    if row:
        if row["deleted_at"] is not None:
            # Tag soft-deletada ocupa o mesmo (parent_id, name) por causa da
            # UNIQUE constraint — reativa em vez de tentar inserir de novo,
            # senão o INSERT abaixo estoura IntegrityError.
            conn.execute(
                "UPDATE tags SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            conn.commit()
            log.info("Tag reativada após soft-delete: %r (pai=%s)", name, parent_id)
        return row["id"]
    cur = conn.execute(
        "INSERT INTO tags (name, parent_id, color, icon) VALUES (?, ?, ?, ?)",
        (name, parent_id, color, icon),
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


def set_icon(conn: sqlite3.Connection, tag_id: int, icon: str | None) -> None:
    """Nome do ícone (ex.: 'tag-madeira'), ou None para limpar. A coluna
    existe desde o schema v1 mas só ganhou uso na Fatia 33."""
    conn.execute("UPDATE tags SET icon = ?, updated_at = ? WHERE id = ?",
                 (icon, _now(), tag_id))
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
        """SELECT id, parent_id, name, color, icon, sort_order FROM tags
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
    (É como o sidecar restaura tags num banco renascido.)

    Sem cor/ícone (Fatia 45: esse é o motivo de eles não sobreviverem a
    apagar o banco com sidecars ANTIGOS — formato 1 só guardava o nome).
    Sidecars novos (formato 2) usam `get_or_create_chain` abaixo."""
    parent: int | None = None
    tag_id: int | None = None
    for parte in [p.strip() for p in path.split("/") if p.strip()]:
        tag_id = create(conn, parte, parent_id=parent)
        parent = tag_id
    return tag_id


def tag_chain(conn: sqlite3.Connection, tag_id: int) -> list[dict]:
    """Da raiz até `tag_id`: [{"name","color","icon"}, ...] (Fatia 45) —
    o que o sidecar precisa pra CADA elo do caminho sobreviver a apagar o
    banco, não só o nome (`tag_path` já fazia isso, mas descartava cor e
    ícone no meio do caminho)."""
    partes: list[dict] = []
    atual: int | None = tag_id
    while atual is not None:
        row = conn.execute(
            "SELECT name, color, icon, parent_id FROM tags WHERE id = ?", (atual,)
        ).fetchone()
        if row is None:
            break
        partes.append({"name": row["name"], "color": row["color"], "icon": row["icon"]})
        atual = row["parent_id"]
    return list(reversed(partes))


def get_or_create_chain(conn: sqlite3.Connection, chain: list[dict]) -> int | None:
    """Como `get_or_create_path`, mas cada elo carrega cor/ícone (Fatia 45).

    Um elo que JÁ existe no banco não é alterado — `create()` devolve a
    tag existente sem tocar em cor/ícone (mesma regra de "soma, nunca
    substitui" da Fatia 35). Só um elo criado DO ZERO herda a cor/ícone do
    sidecar."""
    parent: int | None = None
    tag_id: int | None = None
    for elo in chain:
        nome = (elo.get("name") or "").strip()
        if not nome:
            continue
        tag_id = create(conn, nome, parent_id=parent,
                        color=elo.get("color"), icon=elo.get("icon"))
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
        """SELECT t.id, t.name, t.parent_id, t.color, t.icon, at.source, at.confidence
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
