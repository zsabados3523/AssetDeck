"""Leitura do espelho .json — o seguro contra perda do banco.

Sidecar corrompido nunca derruba a varredura: é logado e ignorado
(o asset entra como se não houvesse sidecar).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def read_sidecar(path: Path) -> dict | None:
    """Dicionário validado do sidecar, ou None (ausente/ilegível/inválido)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Sidecar ilegível (%s): %s — ignorando.", path, exc)
        return None
    if not isinstance(data, dict) or data.get("assetdeck") != 1:
        log.warning("Sidecar em formato inesperado: %s — ignorando.", path)
        return None
    return data


def restorable_fields(data: dict) -> dict:
    """Extrai APENAS campos seguros para restaurar no banco, já validados.

    Valores fora do contrato (rating 99, notes numérico…) são descartados
    campo a campo — o resto do sidecar ainda aproveita.
    """
    out: dict = {}
    uuid = data.get("uuid")
    if isinstance(uuid, str) and len(uuid) >= 8:
        out["uuid"] = uuid
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        out["name"] = name.strip()
    rating = data.get("rating")
    if isinstance(rating, int) and 1 <= rating <= 5:
        out["rating"] = rating
    if isinstance(data.get("starred"), bool):
        out["starred"] = int(data["starred"])
    notes = data.get("notes")
    if isinstance(notes, str) and notes:
        out["notes"] = notes
    return out
