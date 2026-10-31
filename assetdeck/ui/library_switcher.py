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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.ui import icons, theme


class _LinhaBiblioteca(QWidget):
    """Uma linha do menu: bolinha de "ativa", nome e, abaixo, caminho +
    contagem (Fatia 77).

    Era um `QAction` de UMA linha só — "nome · N assets" — que o Rafael
    chamou de "meio cru". Este formato de duas linhas com a bolinha é o que
    o mockup aprovado da Fatia 70 já previa e ficou pendente desde então
    (estava registrado no checklist do F6).

    É um `QWidget` dentro de um `QWidgetAction` porque `QAction` não desenha
    duas linhas nem um marcador colorido — só texto simples.
    """

    clicked = Signal()

    def __init__(self, nome: str, caminho: str, n_assets: int, ativa: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("libRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(10, 7, 14, 7)
        raiz.setSpacing(10)

        # Bolinha: só a ATIVA acende. O widget existe nas duas para o texto
        # não dançar de lugar entre uma linha e outra.
        bolinha = QLabel()
        bolinha.setObjectName("libDot" if ativa else "libDotOff")
        bolinha.setFixedSize(QSize(8, 8))
        raiz.addWidget(bolinha, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(1)

        rot_nome = QLabel(nome)
        rot_nome.setObjectName("libName" if ativa else "libNameOff")
        textos.addWidget(rot_nome)

        # Caminho elidido no MEIO: o começo ("/home/rafael") e o fim (a pasta
        # da biblioteca) são as duas partes que identificam qual é qual — o
        # miolo é o que pode sumir sem perda.
        metrica = QFontMetrics(rot_nome.font())
        curto = metrica.elidedText(caminho, Qt.TextElideMode.ElideMiddle, 260)
        rot_meta = QLabel(f"{curto}   ·   {n_assets} assets")
        rot_meta.setObjectName("libMeta")
        textos.addWidget(rot_meta)

        raiz.addLayout(textos, 1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class LibrarySwitcher(QToolButton):
    switch_requested = Signal(str)  # root_path escolhido — AINDA não é o ativo

    def __init__(self, conn: sqlite3.Connection, active_library_id: int | None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # objectName próprio (Fatia 77): era "ghost", o mesmo dos ícones
        # soltos do painel — um texto sem ícone nem contorno, que não parecia
        # clicável. Agora tem estilo próprio no QSS, com ícone à esquerda e a
        # seta do menu centrada à direita.
        self.setObjectName("libSwitch")
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(15, 15))
        self._active_library_id = active_library_id
        self.refresh_theme()
        self.refresh(conn, active_library_id)

    def refresh_theme(self) -> None:
        """Reaplica o ícone na cor do modo atual (mesmo padrão dos outros
        widgets que pintam à mão — ver `CategoryButton.refresh_theme`)."""
        self.setIcon(icons.icon("nav-colecoes", theme.current_colors()["text_muted"], 15))

    def refresh(self, conn: sqlite3.Connection, active_library_id: int | None) -> None:
        """Repopula o menu — chamado no início e depois de "Adicionar
        biblioteca…", pra ela aparecer sem precisar reabrir o app."""
        self._active_library_id = active_library_id
        self._menu.clear()
        found_active = False
        for lib in libraries_repo.list_all(conn):
            n = assets_repo.count_for_library(conn, lib["id"])
            ativa = lib["id"] == active_library_id
            linha = _LinhaBiblioteca(lib["name"], lib["root_path"], n, ativa)
            linha.setToolTip(lib["root_path"])
            root = lib["root_path"]
            # Fechar o menu é responsabilidade nossa: um `QWidgetAction` não
            # fecha sozinho ao clicar, ao contrário de um `QAction` normal.
            linha.clicked.connect(
                lambda r=root, a=ativa: (self._menu.close(), self._escolher(r, a)))
            acao = QWidgetAction(self._menu)
            acao.setDefaultWidget(linha)
            self._menu.addAction(acao)
            if ativa:
                self.setText(lib["name"])
                found_active = True
        if not found_active:
            self.setText("Sem biblioteca")
        self._menu.addSeparator()
        # Continua `QAction` normal de propósito: é a única entrada que o
        # teclado ainda alcança (um `QWidgetAction` sai da navegação por
        # setas), e é a ação destrutiva-por-engano menos provável.
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
        if not self._active_library_id:
            self.switch_requested.emit(escolhido)
