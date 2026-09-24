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
        self.setWindowTitle("Gerenciar propriedades")
        self.resize(360, 420)

        self.list = QListWidget()
        self.list.setObjectName("cardFlat")
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self._reload()

        nova_btn = QPushButton("Nova propriedade…")
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
            layout, "Propriedades dos assets",
            "Gerencie os campos personalizados da biblioteca.")
        layout.addWidget(self.list)
        layout.addWidget(botoes)

    def _reload(self) -> None:
        self.list.clear()
        for d in properties_repo.list_defs(self._conn):
            item = QListWidgetItem(f"{d['name']}  ({_TIPO_LABEL[d['value_type']]})")
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
        menu.addAction("Renomear…", lambda: self._renomear(def_id, nome))
        menu.addAction("Excluir", lambda: self._excluir(def_id, nome))
        menu.exec(self.list.mapToGlobal(pos))

    def _nova(self) -> None:
        nome, ok = QInputDialog.getText(self, "Nova propriedade", "Nome:")
        if not (ok and nome.strip()):
            return
        label_tipo, ok = QInputDialog.getItem(
            self, "Tipo da propriedade", "Tipo:",
            list(_TIPO_LABEL.values()), 0, editable=False,
        )
        if not ok:
            return
        try:
            properties_repo.create_def(self._conn, nome, _LABEL_TIPO[label_tipo])
        except ValueError as exc:
            QMessageBox.warning(self, "Não deu", str(exc))
            return
        self.changed = True
        self._reload()

    def _renomear(self, def_id: int, atual: str) -> None:
        nome, ok = QInputDialog.getText(self, "Renomear propriedade", "Novo nome:", text=atual)
        if not (ok and nome.strip()):
            return
        try:
            properties_repo.rename_def(self._conn, def_id, nome)
        except ValueError as exc:
            QMessageBox.warning(self, "Não deu", str(exc))
            return
        self.changed = True
        self._reload()

    def _excluir(self, def_id: int, nome: str) -> None:
        resp = QMessageBox.question(
            self, "Excluir propriedade",
            f"Excluir '{nome}'? Os valores já preenchidos nos assets somem "
            "da tela (o dado fica no banco, é soft delete, como tudo aqui).",
        )
        if resp == QMessageBox.StandardButton.Yes:
            properties_repo.soft_delete_def(self._conn, def_id)
            self.changed = True
            self._reload()
