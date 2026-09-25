"""Navegação lateral da biblioteca.

Pastas, tags, coleções e coleções inteligentes compartilham uma coluna. Cada
seção tem contador e pode ser recolhida ou redimensionada. O controlador de
visibilidade continua disponível para a janela de configurações, sem
acrescentar uma barra de ícones à navegação.

Contagem: cada view tem exatamente UMA linha sintética no topo ("Biblioteca
(tudo)", "(sem filtro de tag)", "(sem filtro de coleção)", "(nenhuma
aplicada)"), então contar tudo e descontar 1 vale para as quatro. Contar a
partir da view em vez de consultar o banco é de propósito: o número não pode
divergir do que está desenhado logo abaixo dele.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSplitter,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from assetdeck.ui import icons, theme

log = logging.getLogger(__name__)

LARGURA_RAIL = 32   # 44 -> 38 (Fatia 95) -> 32 (Fatia 95b, "deixe eles mais apertados")
TAM_ICONE_RAIL = 18   # encolheu pra 16 na Fatia 95b e voltou na 96b:
                      # ficaram pequenos demais na tela do Rafael.
TAM_CHEVRON = 10


def contar_itens(view) -> int:
    """Itens reais de uma view lateral, descontando a linha sintética do topo.

    Nunca negativo: uma view ainda não carregada tem zero itens, e "-1" no
    cabeçalho seria pior do que "0".
    """
    if isinstance(view, QListWidget):
        total = view.count()
    elif isinstance(view, QTreeWidget):
        total = 0
        it = QTreeWidgetItemIterator(view)
        while it.value():
            total += 1
            it += 1
    else:
        log.error("Não sei contar itens de %s na lateral.", type(view).__name__)
        return 0
    return max(0, total - 1)


class SectionHeader(QWidget):
    """Cabeçalho clicável: chevron, título e contador.

    É um QWidget com `mouseReleaseEvent` em vez de um QPushButton porque o
    contador precisa ficar alinhado à direita, e um botão do Qt não sabe
    distribuir texto nas duas pontas sem gambiarra de espaços.
    """

    clicked = Signal()

    def __init__(self, titulo: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(titulo)
        self.setAccessibleDescription("Expandir ou recolher seção")
        self._recolhida = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        self.chevron = QLabel()
        self.chevron.setFixedWidth(TAM_CHEVRON)
        self.titulo = QLabel(titulo)
        self.titulo.setObjectName("sidebarSectionTitle")
        self.contador = QLabel("0")
        self.contador.setObjectName("sidebarCount")

        layout.addWidget(self.chevron)
        layout.addWidget(self.titulo)
        layout.addStretch(1)
        layout.addWidget(self.contador)

        self.refresh_theme()

    def set_count(self, n: int) -> None:
        self.contador.setText(str(n))

    def set_collapsed(self, recolhida: bool) -> None:
        self._recolhida = recolhida
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Redesenha o chevron na cor do modo atual.

        Pinta em Python (não passa pelo QSS), então entra na lista de widgets
        que `MainWindow._refresh_theme_dependent_widgets()` reavisa quando o
        Rafael troca claro/escuro.
        """
        cor = theme.current_colors()["text_muted"]
        pix = icons.pixmap("chevron-down", cor=cor, tam=TAM_CHEVRON)
        if self._recolhida:
            from PySide6.QtGui import QTransform

            pix = pix.transformed(QTransform().rotate(-90), Qt.TransformationMode.SmoothTransformation)
        self.chevron.setPixmap(pix)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class SidebarSection(QWidget):
    """Cabeçalho + view. Recolher esconde a view e deixa só o cabeçalho."""

    collapsed_changed = Signal(bool)

    def __init__(self, chave: str, titulo: str, view: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.view = view
        self._recolhida = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(titulo)
        self.header.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self.header)
        layout.addWidget(view, stretch=1)

        # O contador escuta o MODELO da view, não os `reload()` do
        # MainWindow. As views laterais recarregam a partir de sete pontos
        # diferentes (indexação, criar tag, apagar coleção, salvar smart
        # collection...) e chamar a recontagem em cada um deles é um convite a
        # esquecer o oitavo — o número ficaria mentindo sobre a lista logo
        # abaixo dele. Ligado aqui, não tem como divergir.
        # A recontagem é ADIADA e coalescida (Fatia 87). Ligar `rowsInserted`
        # direto em `refresh_count` custava O(n²): cada pasta inserida
        # percorria a árvore inteira pra contar. Com a biblioteca real do
        # Rafael — 28.520 pastas — isso vira 813 MILHÕES de iterações e o app
        # simplesmente não abria ("é normal que o programa nem abra?").
        #
        # `blockSignals(True)` na view NÃO resolve: quem emite `rowsInserted`
        # é o MODELO, e bloquear o widget não bloqueia o modelo dele.
        #
        # Um QTimer de intervalo zero reinicia a cada sinal, então uma carga
        # de 28 mil inserções termina em UMA contagem, depois que a fila de
        # eventos esvazia.
        self._recontagem = QTimer(self)
        self._recontagem.setSingleShot(True)
        self._recontagem.setInterval(0)
        self._recontagem.timeout.connect(self.refresh_count)

        modelo = view.model()
        for sinal in (modelo.rowsInserted, modelo.rowsRemoved,
                      modelo.modelReset, modelo.layoutChanged):
            sinal.connect(self._agendar_recontagem)
        self.refresh_count()

    def _agendar_recontagem(self, *_args) -> None:
        """Pede uma recontagem pro fim da fila de eventos. Chamadas seguidas
        se fundem numa só — é isso que tira o custo quadrático."""
        self._recontagem.start()

    def refresh_count(self) -> None:
        """Reconta AGORA. Continua público: `Sidebar.refresh_counts()` e o
        `MainWindow` chamam direto quando querem o número na hora."""
        self.header.set_count(contar_itens(self.view))

    def is_collapsed(self) -> bool:
        return self._recolhida

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._recolhida)

    def set_collapsed(self, recolhida: bool) -> None:
        if recolhida == self._recolhida:
            return
        self._recolhida = recolhida
        self.view.setVisible(not recolhida)
        self.header.set_collapsed(recolhida)

        # Sem travar a altura, o QSplitter continua reservando o espaço da
        # view escondida e recolher não devolve altura nenhuma — que é o único
        # motivo de recolher existir.
        if recolhida:
            self.setMaximumHeight(self.header.sizeHint().height())
        else:
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        self.collapsed_changed.emit(recolhida)

    def refresh_theme(self) -> None:
        self.header.refresh_theme()


class SidebarRail(QWidget):
    """Coluna estreita de ícones à esquerda, um por seção.

    Cada botão é marcável e reflete a visibilidade da seção — marcado = seção
    na tela. Mesma semântica dos toggles da janela de configurações (Fatia
    67, era o menu Janela), que continuam existindo e ficam sincronizados
    com estes.
    """

    section_toggled = Signal(str, bool)
    # Engrenagem no PÉ do rail (Fatia 67, ajuste pós-tela: o Rafael pediu
    # canto inferior-esquerdo em vez do canto da barra de menus) — abre a
    # SettingsWindow. Sinal em vez de MainWindow ler o botão direto: o rail
    # não deveria saber que a MainWindow existe.
    settings_clicked = Signal()

    def __init__(self, secoes: list[tuple[str, str, str]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarRail")
        self.setFixedWidth(LARGURA_RAIL)

        layout = QVBoxLayout(self)
        # Centralizados no rail (Fatia 96b). A Fatia 96 tinha encostado os
        # ícones à esquerda com margens desiguais, interpretando "ir um pouco
        # para o lado" como afastá-los do painel de pastas. Era o contrário:
        # o incômodo era o TAMANHO deles, não a posição — voltaram aos 18px
        # de antes e ficam no meio da coluna, com folga igual dos dois lados.
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(2)   # 4 antes — "mais apertados" (Fatia 95b)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.buttons: dict[str, QToolButton] = {}
        self._icones: dict[str, str] = {}
        for chave, nome_icone, dica in secoes:
            b = QToolButton()
            b.setObjectName("railButton")
            b.setCheckable(True)
            b.setChecked(True)
            b.setIconSize(QSize(TAM_ICONE_RAIL, TAM_ICONE_RAIL))
            b.setToolTip(dica)
            b.toggled.connect(lambda visivel, k=chave: self.section_toggled.emit(k, visivel))
            layout.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.buttons[chave] = b
            self._icones[chave] = nome_icone
        layout.addStretch(1)

        # O stretch acima empurra este botão pro FIM da coluna — é o que
        # deixa a engrenagem no canto inferior-esquerdo da janela (o rail
        # já mora na borda esquerda).
        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("railButton")
        self.settings_btn.setIconSize(QSize(TAM_ICONE_RAIL, TAM_ICONE_RAIL))
        self.settings_btn.setToolTip("Configurações")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.refresh_theme()

    def set_checked(self, chave: str, marcado: bool) -> None:
        """Sincroniza sem reemitir o sinal (evita laço com o menu Janela)."""
        b = self.buttons.get(chave)
        if b is None:
            log.error("Seção '%s' não existe no rail da lateral.", chave)
            return
        b.blockSignals(True)
        b.setChecked(marcado)
        b.blockSignals(False)

    def refresh_theme(self) -> None:
        """Ícones pré-tingidos (não passam pelo QSS, que não alcança QIcon).

        Seção na tela = ícone na cor do texto; seção escondida = ícone
        apagado. Deliberadamente SEM a cor de destaque: as quatro seções
        aparecem visíveis por padrão, então pintar "visível" de azul deixava
        quatro ícones acesos o tempo todo — azul virava o estado normal e
        parava de significar coisa alguma. Neste projeto cor só entra onde
        carrega informação, e aqui a informação é a exceção (escondida), não
        a regra.
        """
        pal = theme.current_colors()
        for chave, b in self.buttons.items():
            cor = pal["text"] if b.isChecked() else pal["text_disabled"]
            b.setIcon(icons.icon(self._icones[chave], cor, TAM_ICONE_RAIL))
        # A engrenagem não é toggle de visibilidade — fica sempre na cor
        # apagada (mesma dos ícones "escondidos" acima), nunca destacada.
        self.settings_btn.setIcon(
            icons.icon("settings", pal["text_disabled"], TAM_ICONE_RAIL))


class Sidebar(QWidget):
    """Navegação compacta com as seções existentes da biblioteca."""

    def __init__(self, secoes: list[tuple[str, str, str, QWidget]], parent=None) -> None:
        """`secoes`: (chave, título, nome do ícone, view)."""
        super().__init__(parent)

        # Os botões de visibilidade continuam como API interna para
        # Configurações e compatibilidade, mas o rail vertical saiu da tela:
        # a navegação agora é feita pelas seções nomeadas da própria lateral.
        self.rail = SidebarRail([(c, ic, t) for c, t, ic, _v in secoes], self)
        self.rail.hide()
        self.rail.section_toggled.connect(self._on_rail_toggled)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(1)
        self.sections: dict[str, SidebarSection] = {}
        for chave, titulo, _icone, view in secoes:
            secao = SidebarSection(chave, titulo, view)
            secao.collapsed_changed.connect(self.rail.refresh_theme)
            self.splitter.addWidget(secao)
            self.sections[chave] = secao

        self.setObjectName("sidebarPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.heading = QLabel("Biblioteca")
        self.heading.setObjectName("sidebarHeading")
        self.quick_actions = QWidget()
        self._quick_layout = QVBoxLayout(self.quick_actions)
        self._quick_layout.setContentsMargins(0, 0, 0, 0)
        self._quick_layout.setSpacing(3)
        self._quick_actions_added = False
        self._divider = QFrame()
        self._divider.setObjectName("sidebarRule")
        self._divider.setFixedHeight(1)

        self.rail.settings_btn.setText("Configurações")
        self.rail.settings_btn.setObjectName("sidebarSettings")
        self.rail.settings_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.rail.settings_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 14, 9)
        layout.setSpacing(10)
        layout.addWidget(self.heading)
        layout.addWidget(self.quick_actions)
        layout.addWidget(self._divider)
        layout.addWidget(self.splitter, stretch=1)
        layout.addWidget(self.rail.settings_btn)

        self.setMinimumWidth(self._largura_minima())

    def _largura_minima(self) -> int:
        """Piso derivado do cabeçalho mais largo e dos controles da lateral."""
        maior = max(
            (s.header.sizeHint().width() for s in self.sections.values()),
            default=0,
        )
        margens = self.layout().contentsMargins()
        folga = margens.left() + margens.right() + 2
        largura_rapida = max(
            self.heading.sizeHint().width(),
            self.rail.settings_btn.sizeHint().width(),
            maior,
        )
        return largura_rapida + folga

    def add_quick_action(self, widget: QWidget) -> None:
        """Insere um atalho nomeado entre o título e as seções da lateral."""
        self._quick_layout.addWidget(widget)
        if not self._quick_actions_added:
            self.quick_actions.setVisible(True)
            self._quick_actions_added = True

    # ---- contagem ----

    def refresh_counts(self) -> None:
        for secao in self.sections.values():
            secao.refresh_count()

    # ---- visibilidade (rail e menu Janela falam a mesma língua) ----

    def _on_rail_toggled(self, chave: str, visivel: bool) -> None:
        self.set_section_visible(chave, visivel, sincronizar_rail=False)

    def set_section_visible(self, chave: str, visivel: bool, *,
                            sincronizar_rail: bool = True) -> None:
        secao = self.sections.get(chave)
        if secao is None:
            log.error("Seção '%s' não existe na lateral.", chave)
            return
        secao.setVisible(visivel)
        if sincronizar_rail:
            self.rail.set_checked(chave, visivel)
        self.rail.refresh_theme()

    def section_widget(self, chave: str) -> SidebarSection | None:
        return self.sections.get(chave)

    def refresh_theme(self) -> None:
        self.rail.refresh_theme()
        for secao in self.sections.values():
            secao.refresh_theme()
