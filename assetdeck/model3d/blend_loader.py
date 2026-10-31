"""Leitura de geometria de `.blend` — via o próprio Blender, não um
parser do formato binário fechado (não existe biblioteca de terceiros
confiável pra isso). O app já depende do Blender (renderiza capas,
Fatia 16/38) — reusa a mesma peça pra "ler" o `.blend` também.

Cacheado por `content_hash` (mesma ideia de `thumbs/cache.py`): reabrir o
mesmo `.blend` sem ele ter mudado reaproveita o OBJ. Para caches antigos,
o Blender gera uma vez só o manifesto pequeno de materiais, sem refazer
a geometria.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from assetdeck.blender.render import blender_command, export_material_manifest, export_to_obj
from assetdeck.model3d.assimp_loader import load_via_assimp
from assetdeck.model3d.obj_parser import MaterialRange, Mesh, _resolve_texture, parse_obj

log = logging.getLogger(__name__)


def _cache_path(cache_dir: Path, content_hash: str) -> Path:
    # Novo formato de exportação: não reutilizar OBJ antigo sem UV/MTL.
    return cache_dir / f"{content_hash}-textured-v1.obj"


def _apply_manifest(mesh: Mesh, manifest_path: Path, blend_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.error("Manifesto de materiais inválido para %s: %s",
                  blend_path, manifest_path, exc_info=True)
        return
    if not isinstance(manifest, dict):
        log.error("Manifesto de materiais não é um objeto: %s", manifest_path)
        return
    updated: list[MaterialRange] = []
    for material in mesh.materials:
        info = manifest.get(material.name) if material.name else None
        if not isinstance(info, dict):
            updated.append(material)
            continue
        color = material.color
        values = info.get("color")
        if isinstance(values, list) and len(values) == 3:
            try:
                color = tuple(float(value) for value in values)
            except (TypeError, ValueError):
                log.warning("Cor inválida no manifesto %s: %s", manifest_path,
                            material.name)
        texture = material.texture
        name = info.get("texture")
        if isinstance(name, str) and name:
            texture = _resolve_texture(blend_path.parent, name) or texture
        updated.append(MaterialRange(material.start, material.count, color,
                                     texture, material.name))
    mesh.materials = updated


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
    manifest_path = destino.with_suffix(".materials.json")
    if not manifest_path.is_file():
        result = export_material_manifest(blend_path, destino)
        if not result.ok:
            log.error("Não consegui ler os materiais de %s: %s", blend_path,
                      result.erro)
    try:
        mesh = load_via_assimp(destino)
    except ImportError:
        log.warning("assimp-py indisponível; lendo OBJ do .blend pelo parser Python", exc_info=True)
        mesh = parse_obj(destino)
    if manifest_path.is_file():
        _apply_manifest(mesh, manifest_path, blend_path)
    return mesh
