"""Escolhe o loader certo pela extensão do arquivo — o visualizador
(`ui/model_viewer.py`) só conhece esta função, não os loaders
individuais de cada formato.
"""

from __future__ import annotations

from pathlib import Path

from assetdeck.model3d.obj_parser import Mesh, parse_obj

EXTENSOES_SUPORTADAS = (".obj", ".fbx", ".blend")


def load_mesh(path: Path, content_hash: str | None = None) -> Mesh:
    """`content_hash` só é usado pra `.blend` (chave do cache da
    exportação via Blender, ver `model3d/blend_loader.py`) — as outras
    extensões ignoram o argumento."""
    sufixo = path.suffix.lower()
    if sufixo == ".obj":
        return parse_obj(path)
    if sufixo == ".fbx":
        from assetdeck.model3d.assimp_loader import load_via_assimp

        return load_via_assimp(path)
    if sufixo == ".blend":
        from assetdeck import config
        from assetdeck.model3d.blend_loader import load_via_blender

        if not content_hash:
            raise ValueError("content_hash é obrigatório pra ler .blend (cache)")
        return load_via_blender(path, content_hash, config.models3d_cache_dir())
    raise ValueError(f"Extensão não suportada pelo visualizador 3D: {sufixo}")
