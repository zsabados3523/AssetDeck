"""Leitura de geometria de `.blend` — via o próprio Blender, não um
parser do formato binário fechado (não existe biblioteca de terceiros
confiável pra isso). O app já depende do Blender (renderiza capas,
Fatia 16/38) — reusa a mesma peça pra "ler" o `.blend` também.

Cacheado por `content_hash` (mesma ideia de `thumbs/cache.py`): reabrir o
mesmo `.blend` sem ele ter mudado não chama o Blender de novo — medido
em ~0,4s por chamada (testlib, modelo de móvel), rápido o bastante pra
não travar a UI mas caro demais pra pagar toda vez.
"""

from __future__ import annotations

import logging
from pathlib import Path

from assetdeck.blender.render import blender_command, export_to_obj
from assetdeck.model3d.obj_parser import Mesh, parse_obj

log = logging.getLogger(__name__)


def _cache_path(cache_dir: Path, content_hash: str) -> Path:
    return cache_dir / f"{content_hash}.obj"


def load_via_blender(blend_path: Path, content_hash: str, cache_dir: Path) -> Mesh:
    """Exporta (ou reusa do cache) e lê a geometria de um `.blend`.

    Levanta `RuntimeError` com a mensagem do `export_to_obj` (Blender não
    encontrado, timeout, erro de export) — o chamador (mesmo padrão do
    `_LoadJob` do visualizador) já sabe mostrar isso como "Falhou: …".
    """
    destino = _cache_path(cache_dir, content_hash)
    if not destino.is_file():
        if blender_command() is None:
            raise RuntimeError(
                "Blender não encontrado nesta máquina — é ele quem lê o .blend."
            )
        resultado = export_to_obj(blend_path, destino)
        if not resultado.ok:
            raise RuntimeError(f"Não consegui exportar o .blend: {resultado.erro}")
        log.info("Geometria de %s exportada e cacheada em %s", blend_path.name, destino)
    return parse_obj(destino)
