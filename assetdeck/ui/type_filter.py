"""Filtro de tipos em checklist multi-seleção (sugestão do Rafael).

Um botão que abre uma lista de checkboxes — marcar 'model' + 'texture'
mostra os dois tipos juntos. Clicar nos checkboxes NÃO fecha o menu.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


class TypeFilter(QToolButton):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._checks: dict[str, QCheckBox] = {}
        self._update_label()

    def reload(self, types: list[str]) -> None:
        """Reconstrói o checklist preservando o que estava marcado."""
        marcados = set(self.selected())
        self._menu.clear()
        self._checks = {}

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        for t in types:
            cb = QCheckBox(t)
            cb.setChecked(t in marcados)
            cb.toggled.connect(self._on_toggle)
            layout.addWidget(cb)
            self._checks[t] = cb
        clear = QPushButton("Limpar (mostrar todos)")
        clear.clicked.connect(self._clear)
        layout.addWidget(clear)

        action = QWidgetAction(self._menu)
        action.setDefaultWidget(box)
        self._menu.addAction(action)
        self._update_label()

    def selected(self) -> list[str]:
        """Tipos marcados; lista vazia significa 'todos'."""
        return [t for t, cb in self._checks.items() if cb.isChecked()]

    def _on_toggle(self, _checked: bool) -> None:
        self._update_label()
        self.changed.emit()

    def _clear(self) -> None:
        for cb in self._checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._update_label()
        self._menu.close()
        self.changed.emit()

    def _update_label(self) -> None:
        sel = self.selected() if self._checks else []
        if not sel:
            self.setText("Tipos: todos ▾")
        elif len(sel) == 1:
            self.setText(f"Tipo: {sel[0]} ▾")
        else:
            self.setText(f"Tipos: {len(sel)} marcados ▾")
