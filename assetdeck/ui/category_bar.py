"""Barra de categorias (Fatia 31, refeita) — estilo Connecter.

Uma fileira de botões, um por categoria de asset, com ícone próprio,
rótulo legível e contador. Clicar no CORPO liga/desliga a categoria
inteira; clicar na SETINHA abre o checklist de extensões só daquela
categoria (`MenuButtonPopup`).

Substitui o `TypeFilter` (um botão só, ícone sem rótulo, todos os tipos
espremidos num popup) que o Rafael reprovou vendo na tela: não dava pra
saber o que estava filtrando, e tipo com uma extensão só ficava sem
controle nenhum.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from assetdeck.db.repos import assets as assets_repo
from assetdeck.ui import icons, theme
from assetdeck.ui.categories import CATEGORIES, Category


class CategoryButton(QToolButton):
    """Um botão de categoria: corpo alterna a categoria, setinha abre as
    extensões. Mesmo padrão do `FilterButton` (ícone + QMenu + `:checked`
    do tema), sem QSS novo."""

    changed = Signal()

    def __init__(self, categoria: Category, parent=None) -> None:
        super().__init__(parent)
        self.categoria = categoria
        self._ext_checks: dict[str, QCheckBox] = {}
        self._total = 0

        self.setIcon(icons.icon(categoria.icon, theme.TEXT_MUTED))
        self.setIconSize(QSize(18, 18))
        # Só ícone + setinha (pedido do Rafael depois de ver a barra com os
        # rótulos): nome e contagem vivem no tooltip.
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setCheckable(True)
        self.toggled.connect(self._on_toggled)

        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._sync_label()

    def reload(self, ext_counts: dict[str, int], total: int) -> None:
        """Reconstrói o checklist de extensões preservando o que estava
        marcado. `total` alimenta o contador do rótulo."""
        marcadas = set(self.selected_extensions())
        self._total = total
        self._menu.clear()
        self._ext_checks = {}

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        for ext, n in ext_counts.items():
            cb = QCheckBox(f".{ext}   {n}")
            cb.setChecked(ext in marcadas)
            cb.toggled.connect(self._on_ext_toggled)
            layout.addWidget(cb)
            self._ext_checks[ext] = cb
        if ext_counts:
            limpar = QPushButton("Todas as extensões")
            limpar.clicked.connect(self._clear_extensions)
            layout.addWidget(limpar)

        action = QWidgetAction(self._menu)
        action.setDefaultWidget(box)
        self._menu.addAction(action)

        # Categoria sem nenhum asset fica desabilitada em vez de sumir: a
        # barra não pode dançar de posição quando a biblioteca muda.
        self.setEnabled(total > 0)
        if total == 0 and self.isChecked():
            self.setChecked(False)
        self._sync_label()

    def selected_extensions(self) -> list[str]:
        return [e for e, cb in self._ext_checks.items() if cb.isChecked()]

    def set_state(self, checked: bool, extensions: list[str]) -> None:
        """Restaura estado sem emitir `changed` (mesmo contrato de
        `FilterButton.set_value`)."""
        alvo = {e.lower() for e in extensions}
        self.blockSignals(True)
        self.setChecked(checked and self._total > 0)
        self.blockSignals(False)
        for e, cb in self._ext_checks.items():
            cb.blockSignals(True)
            cb.setChecked(e in alvo)
            cb.blockSignals(False)
        self._sync_label()

    def _on_toggled(self, _checked: bool) -> None:
        self._sync_label()
        self.changed.emit()

    def _on_ext_toggled(self, _checked: bool) -> None:
        # Marcar uma extensão implica querer a categoria: sem isso o filtro
        # ficaria escolhido mas inerte, e o Rafael não veria efeito nenhum.
        if self.selected_extensions() and not self.isChecked():
            self.blockSignals(True)
            self.setChecked(True)
            self.blockSignals(False)
        self._sync_label()
        self.changed.emit()

    def _clear_extensions(self) -> None:
        for cb in self._ext_checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._menu.close()
        self._sync_label()
        self.changed.emit()

    def _sync_label(self) -> None:
        """Sem texto no botão: o tooltip é o único lugar que diz qual
        categoria é e quantos assets ela tem."""
        exts = self.selected_extensions()
        detalhe = (", ".join(f".{e}" for e in exts) if exts
                   else "todas as extensões")
        self.setToolTip(f"{self.categoria.label} — {self._total} assets ({detalhe})")


class CategoryBar(QWidget):
    """Os 6 botões de categoria em linha."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.buttons: dict[str, CategoryButton] = {}
        for categoria in CATEGORIES:
            b = CategoryButton(categoria)
            b.changed.connect(self.changed)
            layout.addWidget(b)
            self.buttons[categoria.key] = b

    def reload(self, conn: sqlite3.Connection, counts: dict[str, int]) -> None:
        """`counts`: contagem por categoria (de `assets_repo.count_by_category`)."""
        for key, b in self.buttons.items():
            ext_counts = assets_repo.extension_counts(
                conn, asset_types=list(b.categoria.asset_types))
            b.reload(ext_counts, counts.get(key, 0))

    def update_counts(self, counts: dict[str, int]) -> None:
        """Só os números — sem remontar os menus (roda a cada filtro aplicado)."""
        for key, b in self.buttons.items():
            b._total = counts.get(key, 0)
            b.setEnabled(b._total > 0 or b.isChecked())
            b._sync_label()

    def selection(self) -> list[dict]:
        """Formato `category_filters` de `assets_repo.list_for_grid`.
        Lista vazia = nenhuma categoria marcada = mostrar tudo."""
        return [
            {"asset_types": list(b.categoria.asset_types),
             "extensions": b.selected_extensions()}
            for b in self.buttons.values() if b.isChecked()
        ]

    def set_selection(self, category_filters: list[dict]) -> None:
        """Restaura de uma Smart Collection. Não emite `changed`."""
        por_tipo = {}
        for grupo in category_filters or []:
            for t in grupo.get("asset_types") or []:
                por_tipo[t] = grupo.get("extensions") or []
        for b in self.buttons.values():
            marcado = any(t in por_tipo for t in b.categoria.asset_types)
            exts: list[str] = []
            for t in b.categoria.asset_types:
                exts.extend(por_tipo.get(t, []))
            b.set_state(marcado, exts)

    def set_selection_from_types(self, asset_types: list[str]) -> None:
        """Smart Collection salva ANTES da Fatia 31 guardou só `asset_types`
        crus — remapeia pros botões pra ela não abrir sem filtro nenhum."""
        alvo = set(asset_types or [])
        for b in self.buttons.values():
            b.set_state(any(t in alvo for t in b.categoria.asset_types), [])
