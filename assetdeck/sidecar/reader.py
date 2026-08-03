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
    if not isinstance(data, dict) or data.get("assetdeck") not in (1, 2):
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
    tags = _restorable_tags(data.get("tags"))
    if tags:
        out["tags"] = tags
    custom = data.get("custom")
    if isinstance(custom, dict):
        # só nome (string não-vazia) → valor de tipo simples (Fatia 22)
        limpo = {
            k.strip(): v for k, v in custom.items()
            if isinstance(k, str) and k.strip() and isinstance(v, (str, int, float, bool))
        }
        if limpo:
            out["custom"] = limpo
    return out


def _restorable_tags(tags) -> list[dict]:
    """Normaliza os dois formatos de sidecar pro MESMO formato de saída —
    `[{"path": "Materiais/Madeira", "chain": [{"name","color","icon"}, ...]}]`
    — pra quem restaura (scanner.py) não precisar saber de qual formato veio.

    Formato 1 (sidecars antigos, `assetdeck: 1`): lista de strings
    ('Materiais/Madeira'). Sem cor/ícone — é exatamente o buraco da
    Fatia 45; a cadeia sai com cor/ícone `None` em cada elo.

    Formato 2 (Fatia 45, `assetdeck: 2`): lista de
    `{"path", "chain": [{"name","color","icon"}, ...]}`.
    """
    if not isinstance(tags, list):
        return []
    normalizados: list[dict] = []
    for t in tags:
        if isinstance(t, str):
            caminho = t.strip()
            if not caminho:
                continue
            chain = [{"name": p, "color": None, "icon": None}
                     for p in caminho.split("/") if p.strip()]
            if chain:
                normalizados.append({"path": caminho, "chain": chain})
        elif isinstance(t, dict):
            caminho = t.get("path")
            chain_bruta = t.get("chain")
            if not isinstance(caminho, str) or not caminho.strip():
                continue
            if not isinstance(chain_bruta, list):
                continue
            chain = []
            for elo in chain_bruta:
                if not isinstance(elo, dict):
                    continue
                nome = elo.get("name")
                if not isinstance(nome, str) or not nome.strip():
                    continue
                cor = elo.get("color") if isinstance(elo.get("color"), str) else None
                icone = elo.get("icon") if isinstance(elo.get("icon"), str) else None
                chain.append({"name": nome.strip(), "color": cor, "icon": icone})
            if chain:
                normalizados.append({"path": caminho.strip(), "chain": chain})
    return normalizados
