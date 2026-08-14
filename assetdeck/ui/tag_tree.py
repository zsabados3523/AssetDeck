"""Árvore de tags: hierarquia, cores, menu de gestão e alvo de drag-and-drop.

Arrastar assets da grid e soltar numa tag = taggear (forma 1 do brief).
"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QColorDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from assetdeck.db.repos import tags as tags_repo
from assetdeck.ui import tag_icons
from assetdeck.ui.tag_dialogs import AliasDialog, TagIconDialog

log = logging.getLogger(__name__)

_TAG_ROLE = 32  # Qt.UserRole
MIME_ASSETS = "application/x-assetdeck-asset-ids"


class TagTree(QTreeWidget):
    tag_selected = Signal(object)          # int da tag, ou None = sem filtro
    assets_dropped = Signal(int, list)     # tag_id, [asset_ids]
    structure_changed = Signal()           # criou/renomeou/excluiu/alias

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = None
        # Só a PRIMEIRA carga abre tudo (bom padrão pra árvore vazia/nova).
        # Dali em diante, reload() preserva o que o Rafael abriu/fechou —
        # senão criar ou apagar uma tag reabria a árvore inteira.
        self._primeira_carga = True
        self.setHeaderHidden(True)
        self.setAcceptDrops(True)
        self.currentItemChanged.connect(self._on_current)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    # ---- dados ----

    def reload(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        expandidas = self._tags_expandidas()
        self.blockSignals(True)
        self.clear()
        raiz = QTreeWidgetItem(["(sem filtro de tag)"])
        raiz.setData(0, _TAG_ROLE, None)
        self.addTopLevelItem(raiz)

        itens: dict[int, QTreeWidgetItem] = {}
        for r in tags_repo.list_tree(conn):
            item = QTreeWidgetItem([r["name"]])
            item.setData(0, _TAG_ROLE, r["id"])
            item.setIcon(0, tag_icons.pixmap_for(r["icon"], r["color"]))
            pai = itens.get(r["parent_id"])
            if pai is not None:
                pai.addChild(item)
            else:
                self.addTopLevelItem(item)
            itens[r["id"]] = item

        if self._primeira_carga:
            # Só quem TEM filho — expandAll() marca folha como expandida
            # também, e esse estado sobra: quando ela ganhasse o primeiro
            # filho depois, apareceria aberta sem o Rafael ter pedido.
            for item in itens.values():
                if item.childCount():
                    item.setExpanded(True)
            self._primeira_carga = False
        else:
            for tag_id, item in itens.items():
                item.setExpanded(tag_id in expandidas)
        self.setCurrentItem(raiz)
        self.blockSignals(False)

    def _tags_expandidas(self) -> set[int]:
        """Ids das tags com o ramo aberto AGORA — capturado antes do
        clear() pra restaurar depois de reconstruir a árvore."""
        expandidas: set[int] = set()
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            tag_id = item.data(0, _TAG_ROLE)
            if tag_id is not None and item.isExpanded():
                expandidas.add(tag_id)
            it += 1
        return expandidas

    def set_expanded(self, ids: set[int]) -> None:
        """Aplica um conjunto de tags expandidas vindo de fora (Fatia 54:
        restaurar da sessão anterior). Espelho de `_tags_expandidas()` —
        assume que a árvore já foi carregada (chamar depois de `reload`)."""
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            tag_id = item.data(0, _TAG_ROLE)
            if tag_id is not None:
                item.setExpanded(tag_id in ids)
            it += 1

    def current_tag_id(self) -> int | None:
        item = self.currentItem()
        return item.data(0, _TAG_ROLE) if item else None

    def _on_current(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is not None:
            self.tag_selected.emit(current.data(0, _TAG_ROLE))

    def select(self, tag_id: int | None) -> None:
        """Seleciona a tag pelo id salvo (ex.: ao aplicar uma Smart
        Collection). Não emite tag_selected — quem chama reaplica o filtro."""
        self.blockSignals(True)
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            if item.data(0, _TAG_ROLE) == tag_id:
                self.setCurrentItem(item)
                break
            it += 1
        self.blockSignals(False)

    # ---- drag-and-drop de assets ----

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        tag_id = item.data(0, _TAG_ROLE) if item else None
        if tag_id is None:
            return
        ids = [int(x) for x in
               bytes(event.mimeData().data(MIME_ASSETS)).decode().split(",") if x]
        if ids:
            self.assets_dropped.emit(tag_id, ids)
            event.acceptProposedAction()

    # ---- gestão (menu de contexto) ----

    def _menu(self, pos) -> None:
        if self._conn is None:
            return
        item = self.itemAt(pos)
        tag_id = item.data(0, _TAG_ROLE) if item else None
        menu = QMenu(self)
        menu.addAction("Nova tag raiz…", lambda: self._nova(None))
        # Não depende de ter clicado numa tag, então fica no nível sempre
        # visível do menu.
        menu.addAction("Aplicar template…", self._template)
        if tag_id is not None:
            menu.addAction("Nova subtag…", lambda: self._nova(tag_id))
            menu.addSeparator()
            menu.addAction("Renomear…", lambda: self._renomear(tag_id, item.text(0)))
            menu.addAction("Cor…", lambda: self._cor(tag_id))
            menu.addAction("Ícone…", lambda: self._icone(tag_id))
            menu.addAction("Aliases (PT/EN)…", lambda: self._aliases(tag_id))
            menu.addSeparator()
            menu.addAction("Excluir (com subtags)", lambda: self._excluir(tag_id, item.text(0)))
        menu.exec(self.mapToGlobal(pos))

    def _nova(self, parent_id: int | None) -> None:
        nome, ok = QInputDialog.getText(self, "Nova tag", "Nome da tag:")
        if ok and nome.strip():
            tags_repo.create(self._conn, nome, parent_id=parent_id)
            self.structure_changed.emit()

    def _renomear(self, tag_id: int, atual: str) -> None:
        nome, ok = QInputDialog.getText(self, "Renomear tag", "Novo nome:", text=atual)
        if ok and nome.strip():
            tags_repo.rename(self._conn, tag_id, nome)
            self.structure_changed.emit()

    def _cor(self, tag_id: int) -> None:
        cor = QColorDialog.getColor(parent=self, title="Cor da tag")
        if cor.isValid():
            tags_repo.set_color(self._conn, tag_id, cor.name())
            self.structure_changed.emit()

    def apply_template_dialog(self) -> None:
        """Ponto de entrada público — usado pelo menu de contexto da árvore
        E pelo menu "Ferramentas" da janela principal (Fatia 36)."""
        self._template()

    def _template(self) -> None:
        from assetdeck.ui.tag_templates_dialog import TagTemplateDialog

        dlg = TagTemplateDialog(self._conn, self)
        if dlg.exec() and dlg.aplicado is not None:
            log.info("Template aplicado: %d criadas, %d já existiam.",
                     dlg.aplicado.criadas, dlg.aplicado.existentes)
            self.structure_changed.emit()

    def _icone(self, tag_id: int) -> None:
        if TagIconDialog(self._conn, tag_id, self).exec():
            self.structure_changed.emit()

    def _aliases(self, tag_id: int) -> None:
        if AliasDialog(self._conn, tag_id, self).exec():
            self.structure_changed.emit()

    def _excluir(self, tag_id: int, nome: str) -> None:
        resp = QMessageBox.question(
            self, "Excluir tag",
            f"Excluir a tag '{nome}' e todas as subtags?\n"
            "(Os assets continuam intactos; é soft delete, como tudo aqui.)",
        )
        if resp == QMessageBox.StandardButton.Yes:
            tags_repo.soft_delete(self._conn, tag_id)
            self.structure_changed.emit()
