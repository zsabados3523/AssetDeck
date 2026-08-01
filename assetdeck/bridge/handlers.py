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


def handle(conn: sqlite3.Connection, library_root: Path, request: dict,
           thumbs_dir: Path | None = None) -> dict:
    """Despacha um comando já decodificado. Nunca levanta: erro vira resposta."""
    cmd = request.get("cmd")
    if cmd not in proto.KNOWN_COMMANDS:
        return proto.error(f"Comando desconhecido: {cmd!r}", code="unknown_command")
    try:
        if cmd == proto.CMD_PING:
            return _ping(library_root)
        if cmd == proto.CMD_LIST_ASSETS:
            return _list_assets(conn, library_root, request, thumbs_dir)
        if cmd == proto.CMD_ASSET_BY_PATH:
            return _asset_by_path(conn, library_root, request, thumbs_dir)
        return _get_asset(conn, library_root, request, thumbs_dir)
    except Exception as exc:
        log.exception("Falha ao tratar comando %r", cmd)
        return proto.error(f"Erro interno ao executar {cmd}: {exc}")


def _thumb_for(row_or_hash, thumbs_dir: Path | None,
               cover_path: str | None = None) -> str | None:
    """Imagem que representa o asset, para o add-on exibir.

    Preferência: capa escolhida pelo Rafael > thumbnail do cache. Devolve
    None se não houver nada pronto (o add-on mostra só o ícone de tipo).
    """
    if cover_path:
        return cover_path
    if thumbs_dir is None or not row_or_hash:
        return None
    from assetdeck.thumbs.cache import thumb_path

    p = thumb_path(Path(thumbs_dir), row_or_hash)
    return str(p) if p.exists() else None


def _ping(library_root: Path) -> dict:
    return proto.ok(
        app="assetdeck", version=__version__, protocol=proto.VERSION,
        library_root=str(library_root),
    )


def _list_assets(conn: sqlite3.Connection, library_root: Path, req: dict,
                 thumbs_dir: Path | None = None) -> dict:
    limit = min(int(req.get("limit") or 200), LIST_LIMIT_MAX)
    tipos = req.get("types") or None
    if tipos is not None and not isinstance(tipos, list):
        return proto.error("'types' deve ser uma lista.", code="bad_request")

    rows = assets_repo.list_for_grid(
        conn, search=req.get("search"), asset_types=tipos,
        min_rating=req.get("min_rating"), starred_only=bool(req.get("starred_only")),
        # O Blender não deve ver os mapas soltos que compõem um material
        # convertido em .blend — só o que o Rafael de fato usa.
        include_dependencies=bool(req.get("include_dependencies", False)),
    )
    total = len(rows)
    itens = [
        {
            "id": r["id"], "uuid": r["uuid"], "name": r["name"],
            "asset_type": r["asset_type"], "rating": r["rating"],
            "starred": bool(r["starred"]), "files_count": r["files_count"],
            "primary_path": str(library_root / r["rel_path"]),
            "cover_path": r["cover_path"],
            "thumb_path": _thumb_for(r["content_hash"], thumbs_dir, r["cover_path"]),
        }
        for r in rows[:limit]
    ]
    return proto.ok(assets=itens, total=total, returned=len(itens))


def _asset_by_path(conn: sqlite3.Connection, library_root: Path, req: dict,
                   thumbs_dir: Path | None = None) -> dict:
    """Arquivo solto no Blender → o asset a que ele pertence (com todos os mapas).

    É o que permite arrastar UM mapa e receber o SET inteiro montado.
    """
    caminho = req.get("path")
    if not isinstance(caminho, str) or not caminho:
        return proto.error("'path' (str) é obrigatório.", code="bad_request")
    try:
        rel = str(Path(caminho).resolve().relative_to(Path(library_root).resolve()))
    except ValueError:
        return proto.error(
            "Esse arquivo não está dentro da biblioteca do AssetDeck.",
            code="outside_library",
        )

    row = conn.execute(
        """SELECT a.id FROM assets a JOIN files f ON f.asset_id = a.id
           WHERE f.rel_path = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
        (rel.replace("\\", "/"),),
    ).fetchone()
    if row is None:
        return proto.error(f"Arquivo não indexado: {rel}", code="not_found")
    return _get_asset(conn, library_root, {"id": row["id"]}, thumbs_dir)


def _get_asset(conn: sqlite3.Connection, library_root: Path, req: dict,
               thumbs_dir: Path | None = None) -> dict:
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
            "thumb_path": _thumb_for(f["content_hash"], thumbs_dir),
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
