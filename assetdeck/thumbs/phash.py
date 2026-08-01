"""Hash perceptual (dHash) — acha a mesma textura em resolução ou formato
diferentes, onde `content_hash` (blake2b do arquivo) não bate (Fatia 20).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_HASH_SIZE = 8  # 8x8 -> 64 bits


def phash_from_image(img) -> str:
    """dHash de 64 bits (hex) a partir de uma imagem PIL já aberta.

    Reamostra pra 9x8 em cinza e compara cada pixel com o vizinho da
    direita — robusto a mudança de resolução/formato/compressão leve.
    """
    small = img.convert("L").resize((_HASH_SIZE + 1, _HASH_SIZE))
    pixels = list(small.getdata())

    valor = 0
    for row in range(_HASH_SIZE):
        offset = row * (_HASH_SIZE + 1)
        for col in range(_HASH_SIZE):
            valor = (valor << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    return f"{valor:016x}"


def compute_phash(path: Path) -> str | None:
    """dHash a partir do caminho — só para arquivos raster; None pro resto
    ou se a imagem não abrir (mesmo padrão de `scanner.image_meta`)."""
    from assetdeck.thumbs.raster import RASTER_EXTS, open_image

    if path.suffix.lower().lstrip(".") not in RASTER_EXTS:
        return None
    try:
        with open_image(path) as img:
            return phash_from_image(img)
    except Exception:
        log.warning("Não consegui calcular phash de %s", path, exc_info=True)
        return None
