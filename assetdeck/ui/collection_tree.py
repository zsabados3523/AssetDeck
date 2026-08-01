"""Árvore de coleções manuais: subpastas, menu de gestão e alvo de drag-and-drop.

Arrastar assets da grid e soltar numa coleção = adicionar à lista (Fatia 17).
"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from assetdeck.db.repos import collections as collections_repo
from assetdeck.ui.asset_grid import MIME_ASSETS

log = logging.getLogger(__name__)

_COLLECTION_ROLE = 32  # Qt.UserRole


class CollectionTree(QTreeWidget):
    collection_selected = Signal(object)   # int da coleção, ou None = sem filtro
    assets_dropped = Signal(int, list)     # collection_id, [asset_ids]
    structure_changed = Signal()           # criou/renomeou/excluiu

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = None
        self.setHeaderHidden(True)
        self.setAcceptDrops(True)
        self.currentItemChanged.connect(self._on_current)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    # ---- dados ----

    def reload(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.blockSignals(True)
        self.clear()
        raiz = QTreeWidgetItem(["(sem filtro de coleção)"])
        raiz.setData(0, _COLLECTION_ROLE, None)
        self.addTopLevelItem(raiz)

        itens: dict[int, QTreeWidgetItem] = {}
        for r in collections_repo.list_tree(conn):
            item = QTreeWidgetItem([r["name"]])
            item.setData(0, _COLLECTION_ROLE, r["id"])
            pai = itens.get(r["parent_id"])
            if pai is not None:
                pai.addChild(item)
            else:
                self.addTopLevelItem(item)
            itens[r["id"]] = item

        self.expandAll()
        self.setCurrentItem(raiz)
        self.blockSignals(False)

    def current_collection_id(self) -> int | None:
        item = self.currentItem()
        return item.data(0, _COLLECTION_ROLE) if item else None

    def _on_current(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is not None:
            self.collection_selected.emit(current.data(0, _COLLECTION_ROLE))

    def select(self, collection_id: int | None) -> None:
        """Seleciona a coleção pelo id salvo (ex.: ao aplicar uma Smart
        Collection). Não emite collection_selected — quem chama reaplica o filtro."""
        self.blockSignals(True)
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            if item.data(0, _COLLECTION_ROLE) == collection_id:
                self.setCurrentItem(item)
                break
            it += 1
        self.blockSignals(False)

    # ---- drag-and-drop de assets ----

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        collection_id = item.data(0, _COLLECTION_ROLE) if item else None
        if collection_id is None:
            return
        ids = [int(x) for x in
               bytes(event.mimeData().data(MIME_ASSETS)).decode().split(",") if x]
        if ids:
            self.assets_dropped.emit(collection_id, ids)
            event.acceptProposedAction()

    # ---- gestão (menu de contexto) ----

    def _menu(self, pos) -> None:
        if self._conn is None:
            return
        item = self.itemAt(pos)
        collection_id = item.data(0, _COLLECTION_ROLE) if item else None
        menu = QMenu(self)
        menu.addAction("Nova coleção raiz…", lambda: self._nova(None))
        if collection_id is not None:
            menu.addAction("Nova subcoleção…", lambda: self._nova(collection_id))
            menu.addSeparator()
            menu.addAction("Renomear…", lambda: self._renomear(collection_id, item.text(0)))
            menu.addSeparator()
            menu.addAction("Excluir (com subcoleções)",
                            lambda: self._excluir(collection_id, item.text(0)))
        menu.exec(self.mapToGlobal(pos))

    def _nova(self, parent_id: int | None) -> None:
        nome, ok = QInputDialog.getText(self, "Nova coleção", "Nome da coleção:")
        if ok and nome.strip():
            collections_repo.create(self._conn, nome, parent_id=parent_id)
            self.structure_changed.emit()

    def _renomear(self, collection_id: int, atual: str) -> None:
        nome, ok = QInputDialog.getText(self, "Renomear coleção", "Novo nome:", text=atual)
        if ok and nome.strip():
            collections_repo.rename(self._conn, collection_id, nome)
            self.structure_changed.emit()

    def _excluir(self, collection_id: int, nome: str) -> None:
        resp = QMessageBox.question(
            self, "Excluir coleção",
            f"Excluir a coleção '{nome}' e todas as subcoleções?\n"
            "(Os assets continuam intactos; é soft delete, como tudo aqui.)",
        )
        if resp == QMessageBox.StandardButton.Yes:
            collections_repo.soft_delete(self._conn, collection_id)
            self.structure_changed.emit()
