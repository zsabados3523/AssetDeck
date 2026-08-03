"""Escrita do espelho .json ao lado do asset.

Regras (SCHEMA.md):
- ÚNICA escrita permitida dentro da biblioteca: criar/atualizar
  `<arquivo-principal>.assetdeck.json`. Nunca tocar nos assets.
- Escrita atômica (tmp + rename): nunca fica um .json pela metade.
- Conteúdo suficiente para reconstruir os metadados se o banco morrer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from uuid import uuid4

from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import tags as tags_repo

log = logging.getLogger(__name__)

# Fatia 45: formato 2 grava cada tag como {"path", "chain":[{"name","color",
# "icon"}, ...]} em vez de só a string do caminho — sem isso, apagar o banco
# e reindexar devolvia as tags cinzas e sem ícone (a cor tinha esse buraco
# desde a Fatia 8; o ícone só herdou o mesmo problema na Fatia 33).
# `sidecar/reader.py` ainda lê sidecars formato 1 (Rafael tem sidecars
# antigos na biblioteca real) — só perde cor/ícone dos elos que ele trazia.
FORMAT_VERSION = 2


def sidecar_path(primary_abs: Path) -> Path:
    """foo.jpg → foo.jpg.assetdeck.json (nome completo evita colisões
    entre foo.jpg e foo.png na mesma pasta)."""
    return primary_abs.with_name(primary_abs.name + ".assetdeck.json")


def write_for_asset(conn: sqlite3.Connection, library_root: Path, asset_id: int) -> Path | None:
    """Escreve/atualiza o sidecar do asset. Retorna o caminho, ou None se
    o arquivo principal está sumido (sem lugar para escrever ao lado)."""
    bundle = assets_repo.get_bundle(conn, asset_id)
    if bundle is None:
        log.error("write_for_asset: asset %d não existe ou está apagado.", asset_id)
        return None
    primary = library_root / bundle["primary_rel_path"]
    if not primary.parent.is_dir():
        log.warning("Sidecar adiado: pasta do asset %d não existe (%s).",
                    asset_id, primary.parent)
        return None

    # Formato 2 (Fatia 45): cada tag do asset com o caminho E a cadeia
    # completa de {name, color, icon} da raiz até ela — não só o nome, como
    # o formato 1 fazia (`bundle["tags"]`, ainda usado pela ponte com o
    # Blender em bridge/handlers.py, que não precisa de cor/ícone).
    tag_ids = [t["id"] for t in tags_repo.tags_of(conn, asset_id)]
    tags_detalhado = [
        {"path": tags_repo.tag_path(conn, tid), "chain": tags_repo.tag_chain(conn, tid)}
        for tid in tag_ids
    ]

    data = {
        "assetdeck": FORMAT_VERSION,
        "uuid": bundle["uuid"],
        "name": bundle["name"],
        "asset_type": bundle["asset_type"],
        "rating": bundle["rating"],
        "starred": bool(bundle["starred"]),
        "notes": bundle["notes"],
        "tags": tags_detalhado,
        "custom": bundle["custom"],   # preenchido quando houver EAV na UI (F3)
        "files": bundle["files"],
    }

    dest = sidecar_path(primary)
    tmp = dest.with_name(f"{dest.name}.{uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("Sidecar escrito: %s", dest)
    return dest
