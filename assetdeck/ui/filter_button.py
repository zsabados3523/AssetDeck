"""Botão de filtro compacto: ícone + popup de escolha ÚNICA.

Mesmo padrão do `TypeFilter` (QToolButton + QMenu), mas pra nota mínima e
resolução mínima — que são escolha única, não checklist. Pedido do Rafael:
tirar "Nota: todas" / "Resolução: todas" da barra de filtros (QComboBox
comprido) e pôr um ícone compacto na linha do breadcrumb.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton

from assetdeck.ui import icons, theme


class FilterButton(QToolButton):
    changed = Signal()

    def __init__(self, icon_name: str, options: list[tuple[str, object]],
                 parent=None) -> None:
        """`options`: [(rótulo, valor), ...] — o PRIMEIRO é o padrão/"sem filtro"."""
        super().__init__(parent)
        self._options = options
        self._default = options[0][1]
        self._value = self._default

        self.setIcon(icons.icon(icon_name, theme.TEXT_MUTED))
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setCheckable(True)  # reaproveita QToolButton:checked do tema —
        # um filtro ativo já se destaca sozinho, sem QSS novo.

        self._menu = QMenu(self)
        self._grupo = QActionGroup(self._menu)
        self._grupo.setExclusive(True)
        self._acoes: list[tuple[QAction, object]] = []
        for rotulo, valor in options:
            acao = QAction(rotulo, self._menu)
            acao.setCheckable(True)
            acao.triggered.connect(lambda _c=False, v=valor: self._select(v))
            self._grupo.addAction(acao)
            self._menu.addAction(acao)
            self._acoes.append((acao, valor))
        self.setMenu(self._menu)

        self._sync_visual()

    def value(self):
        return self._value

    def set_value(self, value) -> None:
        """Restaura um valor salvo (ex.: Smart Collection). Não emite
        `changed` — mesmo contrato de `TypeFilter.set_selected`."""
        self._value = value
        for acao, v in self._acoes:
            acao.blockSignals(True)
            acao.setChecked(v == value)
            acao.blockSignals(False)
        self._sync_visual()

    def _select(self, value) -> None:
        self._value = value
        self._sync_visual()
        self.changed.emit()

    def _sync_visual(self) -> None:
        self.setChecked(self._value != self._default)
        for rotulo, v in self._options:
            if v == self._value:
                self.setToolTip(rotulo)
                break
