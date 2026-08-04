"""Pontinho colorido de status para o rodapé (Fatia 49).

Existe porque o rodapé só dizia "Blender: ouvindo :45017" — texto que obriga a
LER para saber se está tudo bem. Um ponto verde/âmbar/vermelho responde de
relance, que é o que se espera de uma barra de status.

É desenhado em Python (QPainter), não no QSS: um `border-radius` num QLabel
vazio depende de o widget ter fundo estilizado e tamanho fixo, e o resultado
sai serrilhado porque o QSS não antialiasa a borda. Como pinta cor à mão, cai
na armadilha já documentada no REDESIGN-V2 e precisa de `refresh_theme()`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from assetdeck.ui import theme

log = logging.getLogger(__name__)

DIAMETRO = 8

# Estado -> token da paleta. Nomes em vez de cores cruas para o LED continuar
# obedecendo ao tema (e trocar junto no modo escuro).
ESTADOS = {
    "ok": "ok",
    "atencao": "warning",
    "erro": "danger",
    "inativo": "text_disabled",
}


class StatusLed(QWidget):
    def __init__(self, estado: str = "inativo", parent=None) -> None:
        super().__init__(parent)
        self._estado = estado
        self.setFixedSize(QSize(DIAMETRO + 6, DIAMETRO + 6))
        self.refresh_theme()

    def set_estado(self, estado: str) -> None:
        if estado not in ESTADOS:
            log.error("Estado de LED desconhecido: %r (usando 'inativo').", estado)
            estado = "inativo"
        self._estado = estado
        self.refresh_theme()

    def estado(self) -> str:
        return self._estado

    def refresh_theme(self) -> None:
        self._cor = QColor(theme.current_colors()[ESTADOS[self._estado]])
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._cor)
        x = (self.width() - DIAMETRO) / 2
        y = (self.height() - DIAMETRO) / 2
        painter.drawEllipse(QRectF(x, y, DIAMETRO, DIAMETRO))
        painter.end()
