"""Relocalização em lote: arquivos que sumiram do lugar esperado (Fatia 19).

A varredura já grava `missing_since` e `content_hash`, mas não casa os dois
sozinha — se um arquivo indexado é movido para outro caminho, a próxima
varredura cria um asset NOVO (uuid novo, sem tags/nota) no caminho novo e
marca o antigo como sumido. `find_candidates` acha esses pares pelo
content_hash; `relocate` funde o duplicado de volta no asset original,
igual `indexer/grouper.py` já faz para sets PBR (o arquivo é adotado pelo
asset que sobrevive; o asset perdedor leva soft delete).

Só entra assets de UM arquivo (a esmagadora maioria da biblioteca) — sets
multi-arquivo ficam fora do casamento automático nesta fatia.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_candidates(conn: sqlite3.Connection, library_id: int) -> list[dict]:
    """Pares (arquivo sumido, arquivo encontrado em outro lugar) com o
    mesmo content_hash, restritos a assets de um arquivo só dos dois lados
    — mesmo filtro de segurança que `grouper.py` usa para candidatos."""
    rows = conn.execute(
        """SELECT miss.id AS missing_file_id, miss_a.id AS missing_asset_id,
                  miss_a.name AS missing_name, miss.rel_path AS old_rel_path,
                  found.id AS found_file_id, found_a.id AS found_asset_id,
                  found_a.name AS found_name, found.rel_path AS new_rel_path
           FROM files miss
           JOIN assets miss_a ON miss_a.id = miss.asset_id
           JOIN files found ON found.content_hash = miss.content_hash
                            AND found.id != miss.id
           JOIN assets found_a ON found_a.id = found.asset_id
                               AND found_a.id != miss_a.id
           WHERE miss.missing_since IS NOT NULL AND miss.deleted_at IS NULL
             AND miss_a.deleted_at IS NULL AND miss_a.library_id = ?
             AND found.missing_since IS NULL AND found.deleted_at IS NULL
             AND found_a.deleted_at IS NULL AND found_a.library_id = ?
             AND (SELECT COUNT(*) FROM files f2
                  WHERE f2.asset_id = miss_a.id AND f2.deleted_at IS NULL) = 1
             AND (SELECT COUNT(*) FROM files f2
                  WHERE f2.asset_id = found_a.id AND f2.deleted_at IS NULL) = 1
           ORDER BY miss_a.name COLLATE NOCASE""",
        (library_id, library_id),
    ).fetchall()
    return [dict(r) for r in rows]


def relocate(conn: sqlite3.Connection, missing_file_id: int, found_file_id: int) -> int | None:
    """Funde o par: o arquivo achado 'vira' o arquivo do asset que estava
    perdido (ele mantém uuid, tags, nota, favorito); o asset duplicado que
    a varredura tinha criado leva soft delete. Devolve o id do asset
    sobrevivente (para escrever o sidecar), ou None se o par não existe mais."""
    missing = conn.execute(
        "SELECT asset_id FROM files WHERE id = ? AND deleted_at IS NULL",
        (missing_file_id,),
    ).fetchone()
    found = conn.execute(
        "SELECT asset_id FROM files WHERE id = ? AND deleted_at IS NULL",
        (found_file_id,),
    ).fetchone()
    if missing is None or found is None:
        return None

    keeper_id = missing["asset_id"]
    duplicate_id = found["asset_id"]
    now = _now()

    conn.execute("UPDATE files SET deleted_at = ?, updated_at = ? WHERE id = ?",
                 (now, now, missing_file_id))
    conn.execute(
        "UPDATE files SET asset_id = ?, is_primary = 1, updated_at = ? WHERE id = ?",
        (keeper_id, now, found_file_id),
    )
    conn.execute("UPDATE assets SET deleted_at = ?, updated_at = ? WHERE id = ?",
                 (now, now, duplicate_id))
    conn.commit()
    log.info("Asset %d religado: arquivo %d assumiu o lugar do sumido %d "
              "(asset duplicado %d fundido).",
              keeper_id, found_file_id, missing_file_id, duplicate_id)
    return keeper_id
