"""Preview de arquivos vetoriais (pedido do Rafael): só `.svg` tem biblioteca
disponível sem sair do 100% offline — `QtSvg` já vem embutido no PySide6.

`.ai`/`.eps`/`.cdr`/`.dwg` ficam de fora: são formatos proprietários ou
binários complexos, sem biblioteca Python/Qt capaz de ler o conteúdo (DWG em
especial exige o SDK da Open Design Alliance ou um conversor externo — nada
disso é uma dependência razoável pra este projeto).
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

VECTOR_EXTS = {"svg"}


def can_vector(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in VECTOR_EXTS


def render_vector(path: Path, size: int = 256) -> Image.Image:
    """Rasteriza o SVG num quadrado de `size`px, mantendo a proporção
    (a maioria dos SVGs não é quadrada) e centralizado, fundo transparente.
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"SVG inválido ou ilegível: {path}")

    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    tam_svg = renderer.viewBoxF().size()
    if tam_svg.width() <= 0 or tam_svg.height() <= 0:
        tam_svg = renderer.defaultSize()
    if tam_svg.width() <= 0 or tam_svg.height() <= 0:
        alvo = QRectF(0, 0, size, size)
    else:
        escala = min(size / tam_svg.width(), size / tam_svg.height())
        largura, altura = tam_svg.width() * escala, tam_svg.height() * escala
        alvo = QRectF((size - largura) / 2, (size - altura) / 2, largura, altura)

    renderer.render(painter, alvo)
    painter.end()

    # QImage -> PIL via PNG em memória: QImage.save() não aceita um
    # io.BytesIO direto (testado — só QIODevice), então passa por QBuffer.
    from PySide6.QtCore import QBuffer, QIODevice

    qbuf = QBuffer()
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not img.save(qbuf, "PNG"):
        raise RuntimeError(f"Não consegui rasterizar o SVG: {path}")
    buffer = io.BytesIO(bytes(qbuf.data()))
    return Image.open(buffer).convert("RGBA")


def make_vector_thumbnail(src: Path, dest: Path, size: int = 256) -> None:
    imagem = render_vector(src, size)
    imagem.save(dest, "PNG")
