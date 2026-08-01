"""Diálogos de tag: Ctrl+T (taggeamento rápido) e gestão de aliases."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from assetdeck.db.repos import tags as tags_repo

log = logging.getLogger(__name__)

_TAG_ROLE = 32


class QuickTagDialog(QDialog):
    """Ctrl+T: busca + checklist da árvore de tags para o(s) asset(s) selecionado(s).

    Marcado = aplica a todos; desmarcado (antes comum a todos) = remove de
    todos; parcialmente marcado = alguns têm — só muda se você clicar.
    """

    def __init__(self, conn: sqlite3.Connection, asset_ids: list[int], parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._asset_ids = asset_ids
        self.setWindowTitle(f"Tags — {len(asset_ids)} asset(s)  (Ctrl+T)")
        self.resize(360, 480)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar tags…")
        self.search.textChanged.connect(self._filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)

        # Estado inicial: em quantos dos selecionados cada tag está?
        contagem: dict[int, int] = {}
        for aid in asset_ids:
            for t in tags_repo.tags_of(conn, aid):
                contagem[t["id"]] = contagem.get(t["id"], 0) + 1
        self._estado_inicial: dict[int, Qt.CheckState] = {}

        itens: dict[int, QTreeWidgetItem] = {}
        for r in tags_repo.list_tree(conn):
            item = QTreeWidgetItem([r["name"]])
            item.setData(0, _TAG_ROLE, r["id"])
            n = contagem.get(r["id"], 0)
            estado = (Qt.CheckState.Checked if n == len(asset_ids) and n > 0
                      else Qt.CheckState.PartiallyChecked if n > 0
                      else Qt.CheckState.Unchecked)
            item.setCheckState(0, estado)
            self._estado_inicial[r["id"]] = estado
            pai = itens.get(r["parent_id"])
            (pai.addChild(item) if pai else self.tree.addTopLevelItem(item))
            itens[r["id"]] = item
        self.tree.expandAll()

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.tree)
        layout.addWidget(botoes)

    def _filter(self, texto: str) -> None:
        texto = texto.lower().strip()

        def visita(item: QTreeWidgetItem) -> bool:
            proprio = texto in item.text(0).lower()
            filho_visivel = any(visita(item.child(i)) for i in range(item.childCount()))
            item.setHidden(bool(texto) and not (proprio or filho_visivel))
            return proprio or filho_visivel

        for i in range(self.tree.topLevelItemCount()):
            visita(self.tree.topLevelItem(i))

    def apply(self) -> int:
        """Aplica as mudanças; retorna quantas atribuições mudaram."""
        mudancas = 0

        def visita(item: QTreeWidgetItem) -> None:
            nonlocal mudancas
            tid = item.data(0, _TAG_ROLE)
            agora = item.checkState(0)
            antes = self._estado_inicial.get(tid, Qt.CheckState.Unchecked)
            if agora != antes:
                if agora == Qt.CheckState.Checked:
                    for aid in self._asset_ids:
                        tags_repo.assign(self._conn, aid, tid)
                    mudancas += 1
                elif agora == Qt.CheckState.Unchecked:
                    for aid in self._asset_ids:
                        tags_repo.unassign(self._conn, aid, tid)
                    mudancas += 1
            for i in range(item.childCount()):
                visita(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            visita(self.tree.topLevelItem(i))
        return mudancas


class AliasDialog(QDialog):
    """Sinônimos/bilíngue de uma tag: 'madeira' (pt) na tag 'Wood'."""

    def __init__(self, conn: sqlite3.Connection, tag_id: int, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._tag_id = tag_id
        self._mudou = False
        self.setWindowTitle(f"Aliases de: {tags_repo.tag_path(conn, tag_id)}")
        self.resize(340, 360)

        self.lista = QListWidget()
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("novo alias (ex.: madeira)")
        self.lang = QComboBox()
        self.lang.addItem("(sem idioma)", None)
        self.lang.addItem("pt", "pt")
        self.lang.addItem("en", "en")
        add = QPushButton("Adicionar")
        add.clicked.connect(self._add)
        remover = QPushButton("Remover selecionado")
        remover.clicked.connect(self._remove)
        fechar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        fechar.rejected.connect(self.reject)
        fechar.clicked.connect(lambda _b: self.accept() if self._mudou else self.reject())

        linha = QHBoxLayout()
        linha.addWidget(self.campo, stretch=1)
        linha.addWidget(self.lang)
        linha.addWidget(add)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Buscar por qualquer um destes acha a tag:"))
        layout.addWidget(self.lista)
        layout.addLayout(linha)
        layout.addWidget(remover)
        layout.addWidget(fechar)
        self._reload()

    def _reload(self) -> None:
        self.lista.clear()
        for r in tags_repo.aliases_of(self._conn, self._tag_id):
            item = QListWidgetItem(f"{r['alias']}" + (f"  ({r['lang']})" if r["lang"] else ""))
            item.setData(_TAG_ROLE, r["id"])
            self.lista.addItem(item)

    def _add(self) -> None:
        texto = self.campo.text().strip()
        if texto:
            tags_repo.add_alias(self._conn, self._tag_id, texto, self.lang.currentData())
            self.campo.clear()
            self._mudou = True
            self._reload()

    def _remove(self) -> None:
        item = self.lista.currentItem()
        if item is not None:
            tags_repo.remove_alias(self._conn, item.data(_TAG_ROLE))
            self._mudou = True
            self._reload()
