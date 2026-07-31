"""Queries de assets. A UI nunca escreve SQL — sempre passa por aqui."""

from __future__ import annotations

import sqlite3


def count_active(conn: sqlite3.Connection) -> int:
    """Quantos assets existem (soft-deleted não contam)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE deleted_at IS NULL"
    ).fetchone()
    return row["n"]


def list_for_grid(
    conn: sqlite3.Connection,
    search: str | None = None,
    asset_types: list[str] | None = None,
    dir_prefix: str | None = None,
    include_subdirs: bool = True,
) -> list[sqlite3.Row]:
    """Assets para a grid (asset + arquivo principal), com filtros combináveis.

    - search: busca por nome via FTS5 (prefixo, sem diferenciar acentos)
    - asset_types: lista de tipos marcados no checklist ([] ou None = todos)
    - dir_prefix: pasta selecionada na árvore ('' ou None = raiz/tudo)
    - include_subdirs: False = só arquivos diretamente na pasta
    """
    sql = """SELECT a.id, a.uuid, a.name, a.asset_type, a.notes,
                    f.rel_path, f.size_bytes, f.content_hash, f.missing_since
             FROM assets a
             JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
             WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL"""
    params: list = []

    match = _fts_query(search)
    if match:
        sql += " AND a.id IN (SELECT rowid FROM assets_fts WHERE assets_fts MATCH ?)"
        params.append(match)
    if asset_types:
        sql += f" AND a.asset_type IN ({','.join('?' * len(asset_types))})"
        params.extend(asset_types)

    if dir_prefix:
        if include_subdirs:
            sql += " AND f.rel_path LIKE ? ESCAPE '\\'"
            params.append(_like_escape(dir_prefix) + "/%")
        else:
            sql += " AND f.rel_path LIKE ? ESCAPE '\\' AND f.rel_path NOT LIKE ? ESCAPE '\\'"
            params.append(_like_escape(dir_prefix) + "/%")
            params.append(_like_escape(dir_prefix) + "/%/%")
    elif not include_subdirs:
        sql += " AND f.rel_path NOT LIKE '%/%'"  # raiz: só arquivos soltos nela

    sql += " ORDER BY a.name COLLATE NOCASE"
    return conn.execute(sql, params).fetchall()


def distinct_types(conn: sqlite3.Connection) -> list[str]:
    """Tipos de asset presentes no banco (para popular o filtro da UI)."""
    return [
        r["asset_type"]
        for r in conn.execute(
            "SELECT DISTINCT asset_type FROM assets WHERE deleted_at IS NULL ORDER BY 1"
        )
    ]


def set_notes(conn: sqlite3.Connection, asset_id: int, notes: str) -> None:
    """Grava a nota do asset (string vazia = sem nota)."""
    from datetime import datetime, timezone

    conn.execute(
        "UPDATE assets SET notes = ?, updated_at = ? WHERE id = ?",
        (notes or None, datetime.now(timezone.utc).isoformat(), asset_id),
    )
    conn.commit()


def get_bundle(conn: sqlite3.Connection, asset_id: int) -> dict | None:
    """Asset completo para o sidecar: campos + arquivos + tags + custom."""
    a = conn.execute(
        """SELECT id, uuid, name, asset_type, rating, starred, notes
           FROM assets WHERE id = ? AND deleted_at IS NULL""",
        (asset_id,),
    ).fetchone()
    if a is None:
        return None
    files = conn.execute(
        """SELECT rel_path, is_primary FROM files
           WHERE asset_id = ? AND deleted_at IS NULL ORDER BY is_primary DESC""",
        (asset_id,),
    ).fetchall()
    if not files:
        return None
    tags = [
        r["name"]
        for r in conn.execute(
            """SELECT t.name FROM asset_tags at JOIN tags t ON t.id = at.tag_id
               WHERE at.asset_id = ? AND t.deleted_at IS NULL""",
            (asset_id,),
        )
    ]
    return {
        "uuid": a["uuid"], "name": a["name"], "asset_type": a["asset_type"],
        "rating": a["rating"], "starred": a["starred"], "notes": a["notes"],
        "tags": tags,
        "custom": {},  # EAV na UI chega no F3; a estrutura já viaja no sidecar
        "files": [f["rel_path"].rsplit("/", 1)[-1] for f in files],
        "primary_rel_path": files[0]["rel_path"],
    }


def uuid_exists(conn: sqlite3.Connection, uuid: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM assets WHERE uuid = ?", (uuid,)
    ).fetchone() is not None


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Reconstrói o índice de busca a partir dos assets ativos.

    É só índice (reconstruível a qualquer momento, como diz o SCHEMA.md);
    com centenas/milhares de linhas isso custa milissegundos.
    """
    conn.execute("INSERT INTO assets_fts(assets_fts) VALUES('delete-all')")
    conn.execute(
        "INSERT INTO assets_fts(rowid, name, tags) "
        "SELECT id, name, '' FROM assets WHERE deleted_at IS NULL"
    )
    conn.commit()


def _fts_query(search: str | None) -> str | None:
    """Texto do usuário → consulta FTS por prefixo ('conc rus' acha 'Concreto Rústico').

    Tokeniza e remonta com * — assim caracteres especiais do FTS (aspas,
    dois-pontos…) nunca chegam crus à query.
    """
    if not search:
        return None
    import re

    tokens = re.findall(r"\w+", search, flags=re.UNICODE)
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens)


def _like_escape(text: str) -> str:
    """Escapa curingas do LIKE em nomes de pasta ('50%' não pode virar curinga)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
