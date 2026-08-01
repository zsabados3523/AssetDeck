"""Previews customizados: galeria 1:N por asset, com uma capa.

A imagem que o Rafael solta sobre um card é COPIADA para a pasta de dados do
app (~/.local/share/assetdeck/previews) — a biblioteca continua intocada e o
original dele pode ser movido/apagado sem quebrar nada.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add(conn: sqlite3.Connection, asset_id: int, src: Path, dest_dir: Path,
        origin: str = "user", make_cover: bool = True) -> Path:
    """Copia a imagem para a pasta gerenciada e registra na galeria.

    Retorna o caminho da cópia. make_cover=True troca a capa do asset.
    """
    if not src.is_file():
        raise FileNotFoundError(f"Imagem de preview não existe: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = dest_dir / f"{uuid4().hex}{src.suffix.lower()}"
    shutil.copy2(src, stored)

    ordem = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS o FROM previews "
        "WHERE asset_id = ? AND deleted_at IS NULL", (asset_id,),
    ).fetchone()["o"]
    if make_cover:
        conn.execute(
            "UPDATE previews SET is_cover = 0 WHERE asset_id = ?", (asset_id,)
        )
    conn.execute(
        """INSERT INTO previews (asset_id, file_path, kind, origin,
                                 sort_order, is_cover)
           VALUES (?, ?, 'image', ?, ?, ?)""",
        (asset_id, str(stored), origin, ordem, 1 if make_cover else 0),
    )
    conn.commit()
    log.info("Preview %s adicionado ao asset %d (capa=%s): %s",
             origin, asset_id, make_cover, stored.name)
    return stored


def list_for(conn: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, file_path, kind, origin, sort_order, is_cover
           FROM previews WHERE asset_id = ? AND deleted_at IS NULL
           ORDER BY sort_order""",
        (asset_id,),
    ).fetchall()


def set_cover(conn: sqlite3.Connection, preview_id: int) -> None:
    row = conn.execute(
        "SELECT asset_id FROM previews WHERE id = ?", (preview_id,)
    ).fetchone()
    if row is None:
        return
    conn.execute("UPDATE previews SET is_cover = 0 WHERE asset_id = ?",
                 (row["asset_id"],))
    conn.execute("UPDATE previews SET is_cover = 1 WHERE id = ?", (preview_id,))
    conn.commit()


def soft_delete(conn: sqlite3.Connection, preview_id: int) -> None:
    """Tira da galeria (soft delete — o arquivo copiado permanece no disco)."""
    conn.execute(
        "UPDATE previews SET deleted_at = ?, is_cover = 0 WHERE id = ?",
        (_now(), preview_id),
    )
    conn.commit()
