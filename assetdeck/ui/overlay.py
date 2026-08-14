"""Painel-overlay embutido na janela principal (Fatia 65).

Substitui o padrão anterior (`PreviewPopup`/`HdriViewer` em `QDialog` com
`setWindowFlag(Qt.WindowType.Window)`): o Rafael relatou que essas janelas
"piscavam" ao abrir — o compositor remapeia a superfície nativa de uma
janela de topo nova, ainda mais visível na do HDRI (contexto OpenGL
próprio) — e que pareciam "abrir outra janela" (apareciam como item
separado no alt-tab/barra de tarefas), quando o pedido era um preview
integrado ao próprio programa.

`OverlayPanel` é um `QWidget` comum, filho do widget central da janela —
nunca vira janela própria, nunca tem superfície nativa nova. Cobre a área
de conteúdo inteira com um fundo semi-transparente (pintado com
`QPainter`, não `setStyleSheet` — regra do projeto) atrás de um cartão
central onde o conteúdo de verdade mora. Esc ou clicar no fundo fecha; um
clique no CARTÃO não fecha (o cartão é widget filho e recebe o evento
antes de chegar aqui — é a própria propagação de eventos do Qt que separa
os dois casos, sem precisar calcular retângulo nenhum).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class OverlayPanel(QWidget):
    closed = Signal()

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        host.installEventFilter(self)
        self.hide()

    # ---- geometria: sempre do tamanho do host, mesmo se ele for redimensionado
    # com o overlay já aberto ----

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._fit_to_host()
        return super().eventFilter(obj, event)

    def _fit_to_host(self) -> None:
        self.setGeometry(0, 0, self._host.width(), self._host.height())

    def open_overlay(self) -> None:
        self._fit_to_host()
        self.raise_()
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def close_overlay(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    # ---- fundo semi-transparente ----

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))
        super().paintEvent(event)

    # ---- fechar (Esc, clique no fundo) ----

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Só chega aqui quando o clique caiu no FUNDO — um clique em cima do
        # cartão de conteúdo (widget filho) é consumido por ele antes.
        self.close_overlay()
