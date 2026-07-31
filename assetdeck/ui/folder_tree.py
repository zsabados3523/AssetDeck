"""Árvore de pastas da biblioteca (derivada dos rel_path do banco)."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

log = logging.getLogger(__name__)

_DIR_ROLE = 32  # Qt.UserRole


def list_dirs(conn: sqlite3.Connection) -> list[str]:
    """Todas as pastas (e ancestrais) que contêm arquivos indexados."""
    dirs: set[str] = set()
    for row in conn.execute(
        """SELECT DISTINCT f.rel_path FROM files f
           JOIN assets a ON a.id = f.asset_id
           WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL"""
    ):
        parts = row["rel_path"].split("/")[:-1]  # tira o nome do arquivo
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return sorted(dirs)


class FolderTree(QTreeWidget):
    """Seleção de pasta emite dir_selected('' = biblioteca inteira)."""

    dir_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.currentItemChanged.connect(self._on_current)

    def reload(self, conn: sqlite3.Connection) -> None:
        self.blockSignals(True)  # recarregar árvore não deve refiltar a grid
        self.clear()
        root = QTreeWidgetItem(["Biblioteca (tudo)"])
        root.setData(0, _DIR_ROLE, "")
        self.addTopLevelItem(root)

        items: dict[str, QTreeWidgetItem] = {"": root}
        for d in list_dirs(conn):
            parent_path = d.rsplit("/", 1)[0] if "/" in d else ""
            item = QTreeWidgetItem([d.rsplit("/", 1)[-1]])
            item.setData(0, _DIR_ROLE, d)
            items[parent_path].addChild(item)
            items[d] = item

        root.setExpanded(True)
        self.setCurrentItem(root)
        self.blockSignals(False)

    def _on_current(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is not None:
            self.dir_selected.emit(current.data(0, _DIR_ROLE))
