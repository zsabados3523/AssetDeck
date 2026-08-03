"""Diálogo de aplicação de template de tags (Fatia 35).

Mostra a árvore que vai ser criada ANTES de aplicar, marcando o que já
existe — mesmo com a semântica de soma, ver o que vem é a diferença entre
confiar e conferir.
"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from assetdeck.ui import tag_icons, tag_templates, theme

log = logging.getLogger(__name__)


class TagTemplateDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.aplicado: tag_templates.Resultado | None = None
        self.nivel = tag_templates.BALANCEADO

        self.setWindowTitle("Aplicar template de tags — Arquitetura")
        self.resize(440, 560)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        linha = QHBoxLayout()
        for chave, rotulo, _prof in tag_templates.NIVEIS:
            b = QPushButton(rotulo)
            b.setCheckable(True)
            b.setChecked(chave == self.nivel)
            b.clicked.connect(lambda _c=False, k=chave: self._trocar_nivel(k))
            self._grupo.addButton(b)
            linha.addWidget(b)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.setObjectName("cardFlat")

        self.resumo = QLabel()

        self.botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.aplicar_btn = self.botoes.addButton(
            "Aplicar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.aplicar_btn.clicked.connect(self._aplicar)
        self.botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(QLabel(
            "Cria as tags que faltam. As que você já tem ficam intactas — "
            "cor, ícone e assets marcados."))
        layout.addLayout(linha)
        layout.addWidget(self.arvore, stretch=1)
        layout.addWidget(self.resumo)
        layout.addWidget(self.botoes)

        self._recarregar()

    def _trocar_nivel(self, chave: str) -> None:
        self.nivel = chave
        self._recarregar()

    def _recarregar(self) -> None:
        self.arvore.clear()
        pilha: list[QTreeWidgetItem] = []
        novas = existentes = 0

        for no, prof, cor, existe in tag_templates.previa(self._conn, self.nivel):
            rotulo = no.nome + ("   (já existe)" if existe else "")
            item = QTreeWidgetItem([rotulo])
            item.setIcon(0, QIcon(tag_icons.pixmap_for(no.icone, cor)))
            if existe:
                # Cor esmaecida em vez de setDisabled: no Qt, desabilitar um
                # item apaga os FILHOS junto, e aí "Materiais (já existe)"
                # fazia parecer que Madeira/Pedra/Vidro também não viriam.
                item.setForeground(0, QBrush(QColor(theme.current_colors()["text_muted"])))
                existentes += 1
            else:
                novas += 1

            del pilha[prof:]
            if pilha:
                pilha[-1].addChild(item)
            else:
                self.arvore.addTopLevelItem(item)
            pilha.append(item)

        self.arvore.expandAll()
        self.resumo.setText(f"{novas} tags novas · {existentes} já existem")
        self.aplicar_btn.setEnabled(novas > 0)

    def _aplicar(self) -> None:
        self.aplicado = tag_templates.aplicar(self._conn, self.nivel)
        self.accept()
