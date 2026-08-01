"""Lista de coleções inteligentes: buscas salvas, sem hierarquia nem
drag-and-drop de assets — só um gatilho para salvar/aplicar filtros.
"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
)

from assetdeck.db.repos import smart_collections as smart_repo

log = logging.getLogger(__name__)

_SMART_ROLE = Qt.ItemDataRole.UserRole


class SmartCollectionPanel(QListWidget):
    smart_selected = Signal(object)    # int do id, ou None = nenhuma aplicada
    save_requested = Signal(str)       # nome escolhido para salvar os filtros atuais
    structure_changed = Signal()       # renomeou/excluiu

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = None
        self.currentItemChanged.connect(self._on_current)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    # ---- dados ----

    def reload(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.blockSignals(True)
        self.clear()
        raiz = QListWidgetItem("(nenhuma aplicada)")
        raiz.setData(_SMART_ROLE, None)
        self.addItem(raiz)
        for r in smart_repo.list_all(conn):
            item = QListWidgetItem(r["name"])
            item.setData(_SMART_ROLE, r["id"])
            self.addItem(item)
        self.setCurrentItem(raiz)
        self.blockSignals(False)

    def current_smart_id(self) -> int | None:
        item = self.currentItem()
        return item.data(_SMART_ROLE) if item else None

    def _on_current(self, current: QListWidgetItem | None, _prev) -> None:
        if current is not None:
            self.smart_selected.emit(current.data(_SMART_ROLE))

    # ---- gestão (menu de contexto) ----

    def _menu(self, pos) -> None:
        if self._conn is None:
            return
        item = self.itemAt(pos)
        smart_id = item.data(_SMART_ROLE) if item else None
        menu = QMenu(self)
        menu.addAction("Salvar filtros atuais…", self._salvar)
        if smart_id is not None:
            menu.addSeparator()
            menu.addAction("Renomear…", lambda: self._renomear(smart_id, item.text()))
            menu.addAction("Excluir", lambda: self._excluir(smart_id, item.text()))
        menu.exec(self.mapToGlobal(pos))

    def _salvar(self) -> None:
        nome, ok = QInputDialog.getText(self, "Salvar coleção inteligente",
                                        "Nome (ex.: 'HDRIs com nota ≥ 4'):")
        if ok and nome.strip():
            self.save_requested.emit(nome.strip())

    def _renomear(self, smart_id: int, atual: str) -> None:
        nome, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=atual)
        if ok and nome.strip():
            smart_repo.rename(self._conn, smart_id, nome)
            self.structure_changed.emit()

    def _excluir(self, smart_id: int, nome: str) -> None:
        resp = QMessageBox.question(
            self, "Excluir coleção inteligente",
            f"Excluir '{nome}'? (Os filtros salvos somem; nenhum asset é afetado.)",
        )
        if resp == QMessageBox.StandardButton.Yes:
            smart_repo.soft_delete(self._conn, smart_id)
            self.structure_changed.emit()
