"""Diálogo da Fatia 22: criar/renomear/excluir definições de custom properties."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from assetdeck.db.repos import properties as properties_repo
from assetdeck.ui import dialog_chrome

log = logging.getLogger(__name__)

_TIPO_LABEL = {"text": "Texto", "number": "Número", "bool": "Sim/Não", "date": "Data"}
_LABEL_TIPO = {v: k for k, v in _TIPO_LABEL.items()}


class PropertyDefsDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.changed = False
        self.setWindowTitle(self.tr("Gerenciar propriedades"))
        self.resize(360, 420)

        self.list = QListWidget()
        self.list.setObjectName("cardFlat")
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self._reload()

        nova_btn = QPushButton(self.tr("Nova propriedade…"))
        nova_btn.clicked.connect(self._nova)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.addButton(nova_btn, QDialogButtonBox.ButtonRole.ActionRole)
        botoes.rejected.connect(self.accept)
        botoes.accepted.connect(self.accept)
        dialog_chrome.prepare_actions(botoes)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        dialog_chrome.add_heading(
            layout, self.tr("Propriedades dos assets"),
            self.tr("Gerencie os campos personalizados da biblioteca."))
        layout.addWidget(self.list)
        layout.addWidget(botoes)

    def _reload(self) -> None:
        self.list.clear()
        for d in properties_repo.list_defs(self._conn):
            tipo_nome = self.tr(_TIPO_LABEL.get(d["value_type"], d["value_type"]))
            item = QListWidgetItem(f"{d['name']}  ({tipo_nome})")
            item.setData(32, d["id"])
            item.setData(33, d["name"])
            self.list.addItem(item)

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        def_id = item.data(32)
        nome = item.data(33)
        menu = QMenu(self)
        menu.addAction(self.tr("Renomear…"), lambda: self._renomear(def_id, nome))
        menu.addAction(self.tr("Excluir"), lambda: self._excluir(def_id, nome))
        menu.exec(self.list.mapToGlobal(pos))

    def _nova(self) -> None:
        nome, ok = QInputDialog.getText(self, self.tr("Nova propriedade"), self.tr("Nome:"))
        if not (ok and nome.strip()):
            return
        opcoes = [self.tr(v) for v in _TIPO_LABEL.values()]
        label_tipo, ok = QInputDialog.getItem(
            self, self.tr("Tipo da propriedade"), self.tr("Tipo:"),
            opcoes, 0, editable=False,
        )
        if not ok:
            return
        tipo_chave = next(
            (k for k, v in _TIPO_LABEL.items() if self.tr(v) == label_tipo or v == label_tipo),
            "text"
        )
        try:
            properties_repo.create_def(self._conn, nome, tipo_chave)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Não deu"), str(exc))
            return
        self.changed = True
        self._reload()

    def _renomear(self, def_id: int, atual: str) -> None:
        nome, ok = QInputDialog.getText(self, self.tr("Renomear propriedade"), self.tr("Novo nome:"), text=atual)
        if not (ok and nome.strip()):
            return
        try:
            properties_repo.rename_def(self._conn, def_id, nome)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Não deu"), str(exc))
            return
        self.changed = True
        self._reload()

    def _excluir(self, def_id: int, nome: str) -> None:
        resp = QMessageBox.question(
            self, self.tr("Excluir propriedade"),
            self.tr(
                "Excluir '%1'? Os valores já preenchidos nos assets somem "
                "da tela (o dado fica no banco, é soft delete, como tudo aqui)."
            ).arg(nome),
        )
        if resp == QMessageBox.StandardButton.Yes:
            properties_repo.soft_delete_def(self._conn, def_id)
            self.changed = True
            self._reload()
