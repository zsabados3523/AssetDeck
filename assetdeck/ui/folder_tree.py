"""Árvore de pastas da biblioteca (derivada dos rel_path do banco)."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator

log = logging.getLogger(__name__)

_DIR_ROLE = 32  # Qt.UserRole


def list_dirs(conn: sqlite3.Connection, library_id: int | None = None) -> list[str]:
    """Todas as pastas (e ancestrais) que contêm arquivos indexados.

    `library_id`: restringe à biblioteca ativa (Fatia 69) — None = todas
    (comportamento de antes). Sem isso, um banco com mais de uma
    biblioteca indexada mostra pastas que não existem na raiz atual.
    """
    dirs: set[str] = set()
    sql = """SELECT DISTINCT f.rel_path FROM files f
             JOIN assets a ON a.id = f.asset_id
             WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL"""
    params: list = []
    if library_id is not None:
        sql += " AND a.library_id = ?"
        params.append(library_id)
    for row in conn.execute(sql, params):
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

    def reload(self, conn: sqlite3.Connection, library_id: int | None = None) -> None:
        self.blockSignals(True)  # recarregar árvore não deve refiltar a grid
        self.clear()
        root = QTreeWidgetItem(["Biblioteca (tudo)"])
        root.setData(0, _DIR_ROLE, "")
        self.addTopLevelItem(root)

        items: dict[str, QTreeWidgetItem] = {"": root}
        for d in list_dirs(conn, library_id=library_id):
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

    def select(self, dir_prefix: str) -> bool:
        """Seleciona a pasta pelo caminho salvo (ex.: ao aplicar uma Smart
        Collection). Não emite dir_selected — quem chama reaplica o filtro.

        Devolve False se a pasta não existe mais na árvore (sumiu do disco
        entre uma varredura e outra, ou veio de um histórico/Smart
        Collection antigos): quem chama precisa saber pra cair na raiz em
        vez de seguir com a seleção velha e um breadcrumb mentindo."""
        self.blockSignals(True)
        try:
            it = QTreeWidgetItemIterator(self)
            while it.value():
                item = it.value()
                if item.data(0, _DIR_ROLE) == dir_prefix:
                    # Expandir os ancestrais: sem isso a pasta fica
                    # selecionada dentro de um nó fechado e o usuário não vê
                    # onde foi parar.
                    pai = item.parent()
                    while pai is not None:
                        pai.setExpanded(True)
                        pai = pai.parent()
                    self.setCurrentItem(item)
                    self.scrollToItem(item)
                    return True
                it += 1
        finally:
            self.blockSignals(False)
        log.warning("Pasta %r não está mais na árvore — seleção não mudou.",
                    dir_prefix)
        return False
