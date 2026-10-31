"""Botão de filtro compacto: ícone + popup de escolha ÚNICA.

Mesmo padrão do `TypeFilter` (QToolButton + QMenu), mas pra nota mínima e
resolução mínima — que são escolha única, não checklist. Pedido do Rafael:
tirar "Nota: todas" / "Resolução: todas" da barra de filtros (QComboBox
comprido) e pôr um ícone compacto na linha do breadcrumb.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QToolButton

from assetdeck.ui import icons, theme

_SWATCH_SIZE = 16


def _swatch_icon(hex_color: str) -> QIcon:
    """Quadradinho de cor sólida pra opção de menu — mesmo truque de
    `QPixmap.fill(QColor(...))` já usado nas cores de tag (não é
    `setStyleSheet`, então não fere a regra de `ui/theme.py`)."""
    px = QPixmap(_SWATCH_SIZE, _SWATCH_SIZE)
    px.fill(QColor(hex_color))
    return QIcon(px)


class FilterButton(QToolButton):
    changed = Signal()

    def __init__(self, icon_name: str, options: list[tuple[str, object]],
                 parent=None, swatch: bool = False,
                 caption: str | None = None) -> None:
        """`options`: [(rótulo, valor), ...] — o PRIMEIRO é o padrão/"sem filtro".

        `swatch`: True faz cada opção (exceto a padrão) mostrar um
        quadradinho da própria cor (`valor` precisa ser um hex tipo
        "#rrggbb") em vez de só o texto — usado pela paleta de busca por
        cor (Fatia 39)."""
        super().__init__(parent)
        self.setObjectName("toolbarFilter")
        self._options = options
        self._default = options[0][1]
        self._value = self._default
        self._icon_name = icon_name  # guardado pra refresh_theme() (Fatia 43)

        self.setIcon(icons.icon(icon_name, theme.current_colors()["text_muted"]))
        self.setIconSize(QSize(16, 16))
        self.setText(caption or "")
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if caption else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setFixedHeight(34)
        self.setAccessibleName(caption or options[0][0])
        self.setCheckable(True)  # reaproveita QToolButton:checked do tema —
        # um filtro ativo já se destaca sozinho, sem QSS novo.

        self._menu = QMenu(self)
        self._menu.setObjectName("filterPopup")
        self._grupo = QActionGroup(self._menu)
        self._grupo.setExclusive(True)
        self._acoes: list[tuple[QAction, object]] = []
        for rotulo, valor in options:
            acao = QAction(rotulo, self._menu)
            acao.setCheckable(True)
            if swatch and valor is not None:
                acao.setIcon(_swatch_icon(valor))
            acao.triggered.connect(lambda _c=False, v=valor: self._select(v))
            self._grupo.addAction(acao)
            self._menu.addAction(acao)
            self._acoes.append((acao, valor))
        self.setMenu(self._menu)

        self._sync_visual()

    def refresh_theme(self) -> None:
        """Reaplica o ícone com a cor do modo atual (Fatia 43) — chamado
        depois de `theme.apply_theme()` trocar claro/escuro ao vivo."""
        self.setIcon(icons.icon(self._icon_name, theme.current_colors()["text_muted"]))

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
