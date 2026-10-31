"""Ícones SVG do AssetDeck.

Motivo de existir (medido na Fatia 24 com `QRawFont`): nenhuma fonte instalada
na máquina tem o glifo ★ — o Qt cai numa fonte substituta e a estrela sai
torta. Os SVGs aqui resolvem isso, junto com os ícones de ação que hoje são
texto (lupa, atualizar) ou simplesmente não existem (olho cortado, chevron,
check).

Desenhados à mão (não vendorizados): são ~8 glifos geométricos simples, e
desenhar evita depender de licença ou de baixar algo — o que combina com o
"100% offline" do projeto (ver PROJECT.md).
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

log = logging.getLogger(__name__)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    ICONS_DIR = Path(sys._MEIPASS) / "assetdeck" / "ui" / "icons"
else:
    ICONS_DIR = Path(__file__).parent / "icons"


@lru_cache(maxsize=None)
def pixmap(nome: str, cor: str | None = None, tam: int = 20) -> QPixmap:
    """Renderiza um ícone SVG em `tam`×`tam`, recolorido para `cor`.

    A recoloração usa `CompositionMode_SourceIn`: preenche o retângulo todo
    com `cor` e deixa só o alfa do SVG original sobreviver. Assim um único
    arquivo (desenhado em preto) serve para qualquer cor do tema — não é
    preciso um SVG por variante.

    Erro de nome levanta na hora, alto: um ícone que "simplesmente não
    aparece" é mais difícil de depurar do que um `FileNotFoundError` com o
    caminho exato.
    """
    caminho = ICONS_DIR / f"{nome}.svg"
    if not caminho.exists():
        log.error("Ícone '%s' não encontrado (esperado em %s).", nome, caminho)
        raise FileNotFoundError(f"Ícone '{nome}' não existe em {ICONS_DIR}")

    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(caminho))
    if not renderer.isValid():
        log.error("SVG inválido: %s", caminho)
        raise ValueError(f"SVG inválido: {caminho}")

    base = QPixmap(QSize(tam, tam))
    base.fill(Qt.GlobalColor.transparent)
    painter = QPainter(base)
    renderer.render(painter)
    painter.end()

    if not cor:
        return base

    tintado = QPixmap(base.size())
    tintado.fill(Qt.GlobalColor.transparent)
    p = QPainter(tintado)
    p.drawPixmap(0, 0, base)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(tintado.rect(), QColor(cor))
    p.end()
    return tintado


def icon(nome: str, cor: str | None = None, tam: int = 20) -> QIcon:
    return QIcon(pixmap(nome, cor, tam))
