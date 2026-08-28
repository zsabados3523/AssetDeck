"""Leitura e tonemap de HDR/EXR para preview.

- .hdr (Radiance): OpenCV (leitor nativo, offline)
- .exr (OpenEXR):  bindings oficiais OpenEXR (o wheel do OpenCV 5 vem sem
  o codec, e o do imageio exigiria download em runtime — 100% offline é regra)

Tonemap: Reinhard global + gamma 2.2 — suficiente para thumbnails/preview.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")  # antes do import do cv2

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

HDR_EXTS = {"hdr", "exr"}


def can_hdr(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in HDR_EXTS


def load_tonemapped(path: Path) -> Image.Image:
    """Arquivo HDR/EXR → imagem RGB 8-bit já tonemapada (resolução completa)."""
    ext = path.suffix.lower().lstrip(".")
    if ext == "exr":
        rgb = _read_exr(path)
    else:
        img = cv2.imread(str(path), cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
        if img is None:
            raise ValueError(f"OpenCV não conseguiu ler {path}")
        rgb = img[..., ::-1].astype(np.float32)  # BGR → RGB
    return Image.fromarray(_tonemap(rgb), "RGB")


def _read_exr(path: Path) -> np.ndarray:
    import OpenEXR  # import local: só paga o custo quando há .exr

    f = OpenEXR.File(str(path))
    channels = f.channels()
    if "RGBA" in channels:
        return channels["RGBA"].pixels[..., :3].astype(np.float32)
    if "RGB" in channels:
        return channels["RGB"].pixels.astype(np.float32)
    if len(channels) == 1:
        # Mapa de 1 canal (displacement/roughness/altura), comum em texturas
        # PBR — vira escala de cinza replicando o canal único em RGB.
        (canal,) = channels.values()
        cinza = canal.pixels.astype(np.float32)
        return np.repeat(cinza[..., np.newaxis], 3, axis=-1)
    try:
        return np.stack(
            [channels[c].pixels.astype(np.float32) for c in ("R", "G", "B")], axis=-1
        )
    except KeyError as exc:
        raise ValueError(
            f"EXR sem canais RGB reconhecíveis ({sorted(channels)}): {path}"
        ) from exc


def _tonemap(rgb: np.ndarray, key: float = 0.18) -> np.ndarray:
    """Reinhard global: comprime o alcance dinâmico preservando o meio-tom."""
    rgb = np.nan_to_num(np.maximum(rgb, 0.0), posinf=1e4)
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    # Luminância média logarítmica SÓ dos pixels com luz (robusta a sol
    # estourado e a grandes áreas pretas, que arrastariam a média a zero)
    positivos = lum[lum > 1e-6]
    avg = float(np.exp(np.mean(np.log(positivos)))) if positivos.size else 1.0
    scaled = rgb * (key / max(avg, 1e-6))
    mapped = scaled / (1.0 + scaled)
    srgb = np.power(np.clip(mapped, 0.0, 1.0), 1.0 / 2.2)
    return (srgb * 255.0 + 0.5).astype(np.uint8)


def make_hdr_thumbnail(src: Path, dest: Path, size: int = 256) -> None:
    from assetdeck.thumbs.raster import save_png_atomic

    img = load_tonemapped(src)
    img.thumbnail((size, size))
    save_png_atomic(img, dest)
