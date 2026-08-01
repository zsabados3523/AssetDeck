"""Thumbnails de imagens comuns (jpg/png/tif/…) via Pillow.

EXR/HDR precisam de tonemap e chegam na Fatia 7 (imageio+numpy).
"""

from __future__ import annotations

import io
import logging
import zlib
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

# Formatos que o Pillow decodifica com segurança nesta fatia
RASTER_EXTS = {"jpg", "jpeg", "png", "tif", "tiff", "webp", "bmp", "tga", "gif"}

# Texturas 8K+ existem na biblioteca; sem isso o Pillow recusa arquivos grandes
Image.MAX_IMAGE_PIXELS = 300_000_000


def can_thumbnail(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in RASTER_EXTS


def open_image(path: Path) -> Image.Image:
    """Image.open com resgate para PNGs de packs com chunk acessório corrompido.

    Vários packs de assets circulam com o chunk iCCP (perfil de cor) de
    checksum inválido; o Pillow recusa o arquivo inteiro por causa dele.
    O resgate remove EM MEMÓRIA apenas chunks acessórios inválidos — o
    arquivo na biblioteca nunca é tocado (somente-leitura é regra absoluta).
    """
    try:
        return Image.open(path)
    except (UnidentifiedImageError, SyntaxError):
        if path.suffix.lower() != ".png":
            raise
        log.warning("PNG com chunk corrompido, tentando resgate em memória: %s", path)
        return Image.open(io.BytesIO(_sanitize_png(path.read_bytes())))


def _sanitize_png(data: bytes) -> bytes:
    """Reconstrói o PNG em memória descartando chunks ACESSÓRIOS com CRC ruim.

    Chunks críticos (IHDR/PLTE/IDAT/IEND — primeira letra maiúscula) são
    mantidos sempre: se um deles estiver corrompido, o arquivo está
    genuinamente quebrado e o erro deve acontecer.
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data  # não é PNG; devolve como veio e deixa o Pillow decidir
    out = [data[:8]]
    pos = 8
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        end = pos + 12 + length
        chunk = data[pos:end]
        crc_ok = (
            len(chunk) == 12 + length
            and chunk[8 + length:] == zlib.crc32(chunk[4:8 + length]).to_bytes(4, "big")
        )
        critical = 65 <= ctype[0] <= 90  # primeira letra maiúscula
        if crc_ok or critical:
            out.append(chunk)
        else:
            log.warning("Chunk PNG acessório descartado no resgate: %s", ctype.decode("latin1"))
        pos = end
        if ctype == b"IEND":
            break
    return b"".join(out)


def normalize_mode(img: Image.Image) -> Image.Image:
    """Modos exóticos → algo que resize/PNG entendem (16-bit vira 8-bit)."""
    if img.mode in ("I;16", "I;16L", "I;16B", "I;16N", "I", "F"):
        # Mapas 16-bit/float (displacement, roughness…): o resize do
        # Pillow não opera nesses modos — reduz para 8-bit ANTES.
        return img.point(lambda v: v / 256).convert("L") \
            if img.mode.startswith("I") else img.convert("L")
    return img


def save_png_atomic(img: Image.Image, dest: Path) -> None:
    """Escrita atômica com .tmp ÚNICO por chamada: assets duplicados (mesmo
    hash em packs diferentes) geram a mesma thumb em paralelo sem se atropelar."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f"{dest.stem}.{uuid4().hex}.tmp"
    try:
        img.save(tmp, format="PNG")
        tmp.replace(dest)  # atômico; se dois jobs competirem, o último vence
    finally:
        tmp.unlink(missing_ok=True)


def make_thumbnail(src: Path, dest: Path, size: int = 256) -> None:
    """Gera a thumbnail PNG de `src` em `dest` (máx. `size` px, proporção mantida).

    Erros sobem para o chamador logar com contexto.
    """
    with open_image(src) as img:
        img = normalize_mode(img)
        img.thumbnail((size, size))  # in-place, mantém proporção
        if "A" in img.getbands():
            # Cutouts: transparência REAL — o fundo do app aparece por trás
            # (feedback do Rafael; o xadrez da v2 foi descartado)
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "L"):
            img = img.convert("RGB")  # paleta, CMYK etc.
        save_png_atomic(img, dest)
