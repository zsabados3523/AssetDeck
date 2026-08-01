"""Fachada única de preview: raster (Pillow) e HDR/EXR (tonemap) num só lugar.

Quem consome (grid, popup, pipeline) pergunta aqui — sem saber o formato.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from assetdeck.thumbs.hdr import can_hdr, load_tonemapped, make_hdr_thumbnail
from assetdeck.thumbs.raster import (
    can_thumbnail,
    make_thumbnail,
    normalize_mode,
    open_image,
)


def can_preview(path: Path) -> bool:
    """Este arquivo pode virar thumbnail/preview visual?"""
    return can_thumbnail(path) or can_hdr(path)


def make_any_thumbnail(src: Path, dest: Path, size: int = 256) -> None:
    if can_hdr(src):
        make_hdr_thumbnail(src, dest, size)
    else:
        make_thumbnail(src, dest, size)


def load_full_image(path: Path) -> Image.Image:
    """Imagem em resolução completa para o popup (HDR já tonemapado)."""
    if can_hdr(path):
        return load_tonemapped(path)
    img = normalize_mode(open_image(path))
    return img
