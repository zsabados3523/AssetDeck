"""Seletor de biblioteca ativa (Fatia 70).

Substitui o texto fixo "assetdeck-testlib" no canto da faixa de menus por
um botão que lista as bibliotecas conhecidas (`libraries` table) e deixa
trocar de ativa ou anexar uma nova. Mesmo padrão de `FilterButton`
(QToolButton + QMenu) — a diferença é que trocar de opção aqui fecha o
app: a biblioteca ativa é resolvida uma vez só, em `app.py`, antes da
`MainWindow` existir (`ScanController`/`ThumbnailPipeline`/modelo da grade
são todos construídos em cima dela) — reconstruir tudo isso ao vivo é
risco desproporcional ao ganho. `switch_requested` avisa a `MainWindow`,
que confirma com o Rafael e fecha o app; reabrir já traz a biblioteca nova
pelo fluxo normal de inicialização (nada de código novo ali).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QFileDialog, QMenu, QToolButton, QWidget
from PySide6.QtCore import Signal

from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo


class LibrarySwitcher(QToolButton):
    switch_requested = Signal(str)  # root_path escolhido — AINDA não é o ativo

    def __init__(self, conn: sqlite3.Connection, active_library_id: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ghost")  # botão sem moldura, igual às estrelas/ícones do painel
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._active_library_id = active_library_id
        self.refresh(conn, active_library_id)

    def refresh(self, conn: sqlite3.Connection, active_library_id: int) -> None:
        """Repopula o menu — chamado no início e depois de "Adicionar
        biblioteca…", pra ela aparecer sem precisar reabrir o app."""
        self._active_library_id = active_library_id
        self._menu.clear()
        grupo = QActionGroup(self._menu)
        grupo.setExclusive(True)
        for lib in libraries_repo.list_all(conn):
            n = assets_repo.count_for_library(conn, lib["id"])
            ativa = lib["id"] == active_library_id
            acao = QAction(f'{lib["name"]}   ·   {n} assets', self._menu)
            acao.setCheckable(True)
            acao.setChecked(ativa)
            acao.setToolTip(lib["root_path"])
            root = lib["root_path"]
            acao.triggered.connect(
                lambda _c=False, r=root, a=ativa: self._escolher(r, a))
            grupo.addAction(acao)
            self._menu.addAction(acao)
            if ativa:
                self.setText(lib["name"])
        self._menu.addSeparator()
        adicionar = QAction("Adicionar biblioteca…", self._menu)
        adicionar.triggered.connect(lambda: self._adicionar(conn))
        self._menu.addAction(adicionar)

    def _escolher(self, root_path: str, ja_ativa: bool) -> None:
        if not ja_ativa:
            self.switch_requested.emit(root_path)

    def _adicionar(self, conn: sqlite3.Connection) -> None:
        escolhido = QFileDialog.getExistingDirectory(
            self, "Adicionar biblioteca", str(Path.home()))
        if not escolhido:
            return
        libraries_repo.get_or_create(conn, Path(escolhido))
        self.refresh(conn, self._active_library_id)
