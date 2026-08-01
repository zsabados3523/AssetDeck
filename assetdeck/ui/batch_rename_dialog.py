"""Diálogo da Fatia 23: prévia ao vivo de busca-e-substituição em lote.

A única exceção ao somente-leitura do app — por isso a prévia recalcula a
cada tecla, conflitos ficam bem visíveis, e o botão de confirmar só liga
quando não há nada errado.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from assetdeck import batch_rename

_COR_CONFLITO = QColor("#f6c6c6")


class BatchRenameDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, library_id: int,
                 asset_ids: list[int], parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._library_id = library_id
        self._asset_ids = asset_ids
        self._plano: list[batch_rename.RenamePlanItem] = []
        self._conflitos: dict[str, str] = {}
        self.setWindowTitle(f"Renomear em lote — {len(asset_ids)} asset(s)")
        self.resize(700, 460)

        campos = QHBoxLayout()
        self.busca_edit = QLineEdit()
        self.busca_edit.setPlaceholderText("Buscar no nome do arquivo…")
        self.substitui_edit = QLineEdit()
        self.substitui_edit.setPlaceholderText("Substituir por… (vazio remove)")
        campos.addWidget(QLabel("Buscar:"))
        campos.addWidget(self.busca_edit)
        campos.addWidget(QLabel("Substituir por:"))
        campos.addWidget(self.substitui_edit)
        self.busca_edit.textChanged.connect(self._atualizar_previa)
        self.substitui_edit.textChanged.connect(self._atualizar_previa)

        self.info_label = QLabel(
            "Digite o texto a buscar no nome dos arquivos. Nenhum arquivo é "
            "tocado até você clicar em 'Renomear'."
        )
        self.info_label.setWordWrap(True)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Nome atual", "Nome novo"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.botoes = QDialogButtonBox()
        self.renomear_btn = self.botoes.addButton(
            "Renomear", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.botoes.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.renomear_btn.clicked.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.renomear_btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addLayout(campos)
        layout.addWidget(self.info_label)
        layout.addWidget(self.table)
        layout.addWidget(self.botoes)

    def _atualizar_previa(self) -> None:
        busca = self.busca_edit.text()
        substitui = self.substitui_edit.text()
        self._plano = batch_rename.build_plan(
            self._conn, self._asset_ids, busca, substitui
        )
        self._conflitos = batch_rename.find_conflicts(
            self._conn, self._library_id, self._plano
        )

        self.table.setRowCount(len(self._plano))
        for row, item in enumerate(self._plano):
            nome_antigo = item.old_rel_path.rsplit("/", 1)[-1]
            nome_novo = item.new_rel_path.rsplit("/", 1)[-1]
            item_antigo = QTableWidgetItem(nome_antigo)
            item_novo = QTableWidgetItem(nome_novo)
            motivo = self._conflitos.get(item.new_rel_path)
            if motivo:
                item_novo.setText(f"{nome_novo}   ⚠ {motivo}")
                item_antigo.setBackground(_COR_CONFLITO)
                item_novo.setBackground(_COR_CONFLITO)
            self.table.setItem(row, 0, item_antigo)
            self.table.setItem(row, 1, item_novo)

        if not busca:
            self.info_label.setText(
                "Digite o texto a buscar no nome dos arquivos. Nenhum arquivo é "
                "tocado até você clicar em 'Renomear'."
            )
        elif not self._plano:
            self.info_label.setText("Nenhum arquivo bate com essa busca.")
        elif self._conflitos:
            self.info_label.setText(
                f"⚠ {len(self._conflitos)} conflito(s) — ajuste a busca/substituição "
                "antes de renomear (destacado em vermelho)."
            )
        else:
            self.info_label.setText(
                f"{len(self._plano)} arquivo(s) serão renomeados. Nada é tocado "
                "até você confirmar."
            )

        self.renomear_btn.setEnabled(bool(self._plano) and not self._conflitos)
        self.renomear_btn.setText(f"Renomear {len(self._plano)} arquivo(s)")

    def get_plan(self) -> list[batch_rename.RenamePlanItem]:
        return self._plano
