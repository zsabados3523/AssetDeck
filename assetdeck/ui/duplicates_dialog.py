"""Diálogo da Fatia 20: grupos de duplicados por conteúdo visual (phash).

Ação SEMPRE não-destrutiva: marca os selecionados como ocultos
(`assets.hidden`, já reversível via "Mostrar ocultos" desde a Fatia 10b).
Nunca apaga nem sugere apagar arquivo — a biblioteca é somente-leitura.
"""

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


def _resolucao(membro: dict) -> str:
    if membro["width"] and membro["height"]:
        return f"{membro['width']}×{membro['height']}"
    return "—"


class DuplicatesDialog(QDialog):
    def __init__(self, grupos: list[list[dict]], parent=None) -> None:
        super().__init__(parent)
        self._linhas: list[tuple[int, dict]] = []  # (asset_id, membro) por linha marcável
        self.setWindowTitle("Duplicados por conteúdo visual")
        self.resize(720, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        total_itens = sum(len(g) for g in grupos)
        layout.addWidget(QLabel(
            f"{len(grupos)} grupo(s) de mesma textura ({total_itens} asset(s) no total). "
            "Marcado = fica OCULTO da grade (reversível em 'Mostrar ocultos'); nada é "
            "apagado do disco. Por padrão, mantém visível o de maior resolução."
        ))

        self.table = QTableWidget(total_itens + len(grupos), 3)
        self.table.setObjectName("cardFlat")
        self.table.setHorizontalHeaderLabels(["Asset", "Resolução", "Caminho"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        linha = 0
        for grupo in grupos:
            maior = max(grupo, key=lambda m: (m["width"] or 0) * (m["height"] or 0))
            cabecalho = QTableWidgetItem(f"— grupo ({len(grupo)} iguais) —")
            cabecalho.setFlags(Qt.ItemFlag.NoItemFlags)
            self.table.setItem(linha, 0, cabecalho)
            self.table.setSpan(linha, 0, 1, 3)
            linha += 1
            for membro in grupo:
                item_nome = QTableWidgetItem(membro["name"])
                item_nome.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                marcar = membro["asset_id"] != maior["asset_id"]
                item_nome.setCheckState(
                    Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
                )
                self.table.setItem(linha, 0, item_nome)
                self.table.setItem(linha, 1, QTableWidgetItem(_resolucao(membro)))
                self.table.setItem(linha, 2, QTableWidgetItem(membro["rel_path"]))
                self._linhas.append((linha, membro))
                linha += 1
        layout.addWidget(self.table)

        botoes = QDialogButtonBox()
        ocultar = botoes.addButton("Ocultar selecionados", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton(QDialogButtonBox.StandardButton.Cancel)
        ocultar.clicked.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def selected_asset_ids(self) -> list[int]:
        ids = []
        for linha, membro in self._linhas:
            item = self.table.item(linha, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                ids.append(membro["asset_id"])
        return ids
