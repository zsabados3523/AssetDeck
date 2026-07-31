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

log = logging.getLogger(__name__)

FORMAT_VERSION = 1


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

    data = {
        "assetdeck": FORMAT_VERSION,
        "uuid": bundle["uuid"],
        "name": bundle["name"],
        "asset_type": bundle["asset_type"],
        "rating": bundle["rating"],
        "starred": bool(bundle["starred"]),
        "notes": bundle["notes"],
        "tags": bundle["tags"],       # preenchido de verdade na Fatia 8
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
