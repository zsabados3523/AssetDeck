"""Diálogo de revisão da Fatia 19: pares (sumido → encontrado) para religar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from assetdeck.ui import dialog_chrome


class RelocateDialog(QDialog):
    """Tabela de candidatos a religar, todos marcados por padrão. O Rafael
    revisa e desmarca o que não quiser antes de aplicar."""

    def __init__(self, candidatos: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._candidatos = candidatos
        self.setWindowTitle("Relocalizar assets perdidos")
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        dialog_chrome.add_heading(layout, "Relocalizar assets perdidos",
            f"{len(candidatos)} asset(s) sumido(s) batem com um arquivo "
            "encontrado em outro lugar (mesmo conteúdo). Desmarque o que não "
            "quiser religar — nada é apagado do disco; só o banco é ajustado.")

        self.table = QTableWidget(len(candidatos), 3)
        self.table.setObjectName("cardFlat")
        self.table.setHorizontalHeaderLabels(["Asset", "Caminho antigo (sumido)", "Caminho novo"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, c in enumerate(candidatos):
            item_nome = QTableWidgetItem(c["missing_name"])
            item_nome.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            item_nome.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, item_nome)
            self.table.setItem(row, 1, QTableWidgetItem(c["old_rel_path"]))
            self.table.setItem(row, 2, QTableWidgetItem(c["new_rel_path"]))
        layout.addWidget(self.table)

        botoes = QDialogButtonBox()
        religar = botoes.addButton("Religar selecionados", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton(QDialogButtonBox.StandardButton.Cancel)
        religar.clicked.connect(self.accept)
        botoes.rejected.connect(self.reject)
        dialog_chrome.prepare_actions(botoes)
        layout.addWidget(botoes)

    def selected_pairs(self) -> list[tuple[int, int]]:
        pares = []
        for row, c in enumerate(self._candidatos):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                pares.append((c["missing_file_id"], c["found_file_id"]))
        return pares
