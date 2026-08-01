"""Duplicados por conteúdo visual (Fatia 20).

Agrupa assets ativos, visíveis, pelo `phash` do arquivo principal —
diferente do `content_hash`, o phash bate mesmo com a mesma textura salva
de novo em outra resolução ou formato.
"""

from __future__ import annotations

import sqlite3


def find_duplicate_groups(conn: sqlite3.Connection, library_id: int) -> list[list[dict]]:
    """Grupos (2+ assets) com o mesmo phash no arquivo principal."""
    rows = conn.execute(
        """SELECT a.id AS asset_id, a.name, f.rel_path, f.width, f.height, f.phash
           FROM assets a JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND a.hidden = 0
             AND f.deleted_at IS NULL AND f.missing_since IS NULL
             AND f.phash IS NOT NULL
           ORDER BY a.name COLLATE NOCASE""",
        (library_id,),
    ).fetchall()

    grupos: dict[str, list[dict]] = {}
    for r in rows:
        grupos.setdefault(r["phash"], []).append(dict(r))

    return [membros for membros in grupos.values() if len(membros) > 1]
