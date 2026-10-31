"""Capa renderizada de um set PBR, gerada fora da UI e da biblioteca."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

PREVIEW_VERSION = 1
TIMEOUT_S = 120


def preview_key(files: list) -> str:
    """Muda quando qualquer mapa do set muda, sem depender só da capa."""
    parts = sorted((str(f["map_role"]), str(f["content_hash"])) for f in files)
    payload = json.dumps([PREVIEW_VERSION, parts], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def preview_path(thumbs_dir: Path, key: str, size: int = 256) -> Path:
    suffix = "" if size == 256 else f"_{size}"
    return thumbs_dir / f"material_{key}{suffix}.png"


def render_material_preview(name: str, maps: dict[str, Path], dest: Path,
                            cancel: threading.Event | None = None,
                            size: int = 256) -> None:
    """Renderiza em arquivo temporário e publica a capa completa de uma vez."""
    blender = shutil.which("blender")
    if blender is None:
        raise RuntimeError("Blender não encontrado para gerar a capa PBR")
    if size not in (256, 640):
        raise ValueError(f"Tamanho de capa PBR não suportado: {size}")
    for role, path in maps.items():
        if not path.is_file():
            raise FileNotFoundError(f"Mapa {role} não encontrado: {path}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex}.png")
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        script = Path(sys._MEIPASS) / "assetdeck" / "blender" / "scripts" / "render_material_preview.py"
        materials = Path(sys._MEIPASS) / "blender_addon" / "assetdeck_bridge" / "materials.py"
    else:
        script = Path(__file__).parent / "scripts" / "render_material_preview.py"
        materials = Path(__file__).parents[2] / "blender_addon/assetdeck_bridge/materials.py"
    args = [blender, "-b", "-t", "1", "--factory-startup", "-P", str(script),
            "--", str(materials), str(temp), name, str(size),
            json.dumps({role: str(path) for role, path in maps.items()})]
    try:
        with subprocess.Popen(args, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as proc:
            deadline = time.monotonic() + TIMEOUT_S
            while True:
                if cancel is not None and cancel.is_set():
                    proc.terminate()
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise RuntimeError("Render da capa PBR cancelado ao fechar o app")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    proc.communicate()
                    raise TimeoutError(f"Render da capa PBR excedeu {TIMEOUT_S}s")
                try:
                    stdout, stderr = proc.communicate(timeout=min(0.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        if proc.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
            detail = (stderr or stdout or "sem detalhes").strip()[-1500:]
            raise RuntimeError(f"Blender não gerou a capa de {name}: {detail}")
        os.replace(temp, dest)
    finally:
        if temp.exists():
            temp.unlink()
