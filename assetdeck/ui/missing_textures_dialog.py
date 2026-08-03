"""Diálogo de resultado da Fatia 40 — somente leitura.

Sem checkbox, sem ação de "aplicar": não há nada pra escrever. O que o
AssetDeck religa (relocator.py) é o BANCO dele mesmo; o que está quebrado
aqui é referência interna do .blend, fora do alcance de escrita do app
(mesmo motivo do somente-leitura sobre a biblioteca).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class MissingTexturesDialog(QDialog):
    def __init__(self, blend_path: Path, perdidas: list[dict],
                 recuperadas_auto: int, parent=None) -> None:
        super().__init__(parent)
        self._blend_path = blend_path
        self.setWindowTitle(f"Texturas — {blend_path.name}")
        self.resize(640, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        resumo = f"{len(perdidas)} continuam quebradas"
        if recuperadas_auto:
            resumo += f" · {recuperadas_auto} religadas automaticamente ao renderizar"
        layout.addWidget(QLabel(resumo))

        self.table = QTableWidget(len(perdidas), 2)
        self.table.setObjectName("cardFlat")
        self.table.setHorizontalHeaderLabels(["Textura", "Caminho esperado"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, p in enumerate(perdidas):
            self.table.setItem(row, 0, QTableWidgetItem(p["nome"]))
            self.table.setItem(row, 1, QTableWidgetItem(p["caminho_esperado"]))
        layout.addWidget(self.table)

        abrir_pasta = QPushButton("Abrir pasta do asset")
        abrir_pasta.clicked.connect(self._abrir_pasta)
        layout.addWidget(abrir_pasta)

        # Close é RejectRole no Qt — só emite `rejected`, não `accepted`.
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _abrir_pasta(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._blend_path.parent)))
