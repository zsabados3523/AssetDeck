"""Lógica dos comandos da ponte — pura, testável sem socket e sem Qt."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from assetdeck import __version__
from assetdeck.bridge import protocol as proto
from assetdeck.db.repos import assets as assets_repo

log = logging.getLogger(__name__)

LIST_LIMIT_MAX = 500


def handle(conn: sqlite3.Connection, library_root: Path, request: dict) -> dict:
    """Despacha um comando já decodificado. Nunca levanta: erro vira resposta."""
    cmd = request.get("cmd")
    if cmd not in proto.KNOWN_COMMANDS:
        return proto.error(f"Comando desconhecido: {cmd!r}", code="unknown_command")
    try:
        if cmd == proto.CMD_PING:
            return _ping(library_root)
        if cmd == proto.CMD_LIST_ASSETS:
            return _list_assets(conn, library_root, request)
        return _get_asset(conn, library_root, request)
    except Exception as exc:
        log.exception("Falha ao tratar comando %r", cmd)
        return proto.error(f"Erro interno ao executar {cmd}: {exc}")


def _ping(library_root: Path) -> dict:
    return proto.ok(
        app="assetdeck", version=__version__, protocol=proto.VERSION,
        library_root=str(library_root),
    )


def _list_assets(conn: sqlite3.Connection, library_root: Path, req: dict) -> dict:
    limit = min(int(req.get("limit") or 200), LIST_LIMIT_MAX)
    tipos = req.get("types") or None
    if tipos is not None and not isinstance(tipos, list):
        return proto.error("'types' deve ser uma lista.", code="bad_request")

    rows = assets_repo.list_for_grid(
        conn, search=req.get("search"), asset_types=tipos,
        min_rating=req.get("min_rating"), starred_only=bool(req.get("starred_only")),
    )
    total = len(rows)
    itens = [
        {
            "id": r["id"], "uuid": r["uuid"], "name": r["name"],
            "asset_type": r["asset_type"], "rating": r["rating"],
            "starred": bool(r["starred"]), "files_count": r["files_count"],
            "primary_path": str(library_root / r["rel_path"]),
            "cover_path": r["cover_path"],
        }
        for r in rows[:limit]
    ]
    return proto.ok(assets=itens, total=total, returned=len(itens))


def _get_asset(conn: sqlite3.Connection, library_root: Path, req: dict) -> dict:
    asset_id = req.get("id")
    if not isinstance(asset_id, int):
        return proto.error("'id' (int) é obrigatório.", code="bad_request")
    bundle = assets_repo.get_bundle(conn, asset_id)
    if bundle is None:
        return proto.error(f"Asset {asset_id} não existe.", code="not_found")

    arquivos = [
        {
            "path": str(library_root / f["rel_path"]),
            "map_role": f["map_role"],
            "is_primary": bool(f["is_primary"]),
        }
        for f in assets_repo.list_files(conn, asset_id)
    ]
    return proto.ok(
        asset={
            "id": asset_id, "uuid": bundle["uuid"], "name": bundle["name"],
            "asset_type": bundle["asset_type"], "rating": bundle["rating"],
            "starred": bool(bundle["starred"]), "notes": bundle["notes"],
            "tags": bundle["tags"],
        },
        files=arquivos,
    )
