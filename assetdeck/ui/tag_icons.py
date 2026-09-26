"""Ícones pré-definidos de tag (Fatia 33).

A coluna `tags.icon` existe desde o schema v1 e guarda o NOME do ícone
(ex.: 'tag-madeira') — o mesmo que `icons.icon()` consome.

`pixmap_for` é o único lugar que decide como uma tag é desenhada: a
árvore lateral, o painel de detalhes e o diálogo do Ctrl+T chamam esta
função, e é isso que impede os três de divergirem com o tempo.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from PySide6.QtGui import QColor, QPixmap

from assetdeck.ui import icons, theme

log = logging.getLogger(__name__)


class TagIcon(NamedTuple):
    key: str      # o que vai gravado em tags.icon
    label: str    # o que o Rafael lê no seletor


class Secao(NamedTuple):
    titulo: str
    icones: tuple[TagIcon, ...]


def _s(titulo: str, *pares: tuple[str, str]) -> Secao:
    return Secao(titulo, tuple(TagIcon(f"tag-{k}", r) for k, r in pares))


SECOES: tuple[Secao, ...] = (
    _s("Materiais",
       ("madeira", "Madeira"), ("metal", "Metal"), ("pedra", "Pedra"),
       ("tijolo", "Tijolo"), ("concreto", "Concreto"), ("vidro", "Vidro"),
       ("tecido", "Tecido"), ("couro", "Couro"), ("ceramica", "Cerâmica"),
       ("plastico", "Plástico"), ("espelho", "Espelho"), ("papel", "Papel")),
    _s("Natureza",
       ("arvore", "Árvore"), ("arbusto", "Arbusto"), ("flor", "Flor"),
       ("planta", "Planta"), ("folha", "Folha"), ("grama", "Grama")),
    _s("Objetos",
       ("luz", "Luz"), ("camera", "Câmera"), ("movel", "Móvel"),
       ("pincel", "Pincel"), ("som", "Som")),
    _s("Marcadores",
       ("estrela", "Estrela"), ("bandeira", "Bandeira"), ("alerta", "Alerta")),
)

TODOS: tuple[TagIcon, ...] = tuple(i for s in SECOES for i in s.icones)
CHAVES: frozenset[str] = frozenset(i.key for i in TODOS)


def _quadradinho(color: str | None, tam: int) -> QPixmap:
    """O visual de sempre (pré-Fatia 33): quadrado da cor da tag. Continua
    sendo o padrão de quem não escolheu ícone."""
    pix = QPixmap(tam, tam)
    pix.fill(QColor(color) if color else QColor(theme.current_colors()["text_muted"]))
    return pix


def pixmap_for(icon: str | None, color: str | None, tam: int = 16) -> QPixmap:
    """Como uma tag é desenhada: ícone tingido com a cor dela, ou o
    quadradinho colorido quando não há ícone escolhido."""
    if not icon:
        return _quadradinho(color, tam)
    try:
        return icons.pixmap(icon, cor=color or theme.current_colors()["text_muted"], tam=tam)
    except FileNotFoundError:
        # Ícone gravado no banco que não existe mais como arquivo (SVG
        # removido/renomeado). Sem esta guarda, o reload da árvore INTEIRA
        # morreria por causa de uma tag. Cai no quadradinho — e avisa.
        log.warning("Ícone de tag %r não existe mais; usando a cor apenas.", icon)
        return _quadradinho(color, tam)
