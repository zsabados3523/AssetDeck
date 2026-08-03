"""Cor média — usada pelo filtro de busca por cor (Fatia 39).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def dominant_color_from_image(img) -> str:
    """Cor média (hex "#rrggbb") a partir de uma imagem PIL já aberta.

    Reamostra a imagem inteira para 1x1 pixel — o resultado do resize já É
    a média de todos os pixels originais (mesma ideia de "reamostrar em vez
    de calcular pixel a pixel" do phash)."""
    r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


def compute_dominant_color(path: Path) -> str | None:
    """Cor média a partir do caminho — só para arquivos raster; None pro
    resto ou se a imagem não abrir (mesmo padrão de `compute_phash`)."""
    from assetdeck.thumbs.raster import RASTER_EXTS, open_image

    if path.suffix.lower().lstrip(".") not in RASTER_EXTS:
        return None
    try:
        with open_image(path) as img:
            return dominant_color_from_image(img)
    except Exception:
        log.warning("Não consegui calcular cor média de %s", path, exc_info=True)
        return None
