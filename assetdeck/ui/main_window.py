"""Janela principal: grid de thumbnails + painel de detalhes + indexação."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck import __version__
from assetdeck import batch_rename
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import collections as collections_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.db.repos import properties as properties_repo
from assetdeck.db.repos import smart_collections as smart_collections_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer import duplicates as duplicates_finder
from assetdeck.indexer import relocator
from assetdeck.model3d import loader as model3d_loader
from assetdeck.indexer.scanner import ScanStats
from assetdeck.thumbs.hdr import can_hdr
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui import asset_grid
from assetdeck.ui.asset_grid import AssetGridModel, AssetGridView
from assetdeck.ui.batch_rename_dialog import BatchRenameDialog
from assetdeck.ui.collection_tree import CollectionTree
from assetdeck.ui.details_panel import DetailsPanel
from assetdeck.sidecar import writer as sidecar_writer
from assetdeck.ui.duplicates_dialog import DuplicatesDialog
from assetdeck.ui.filter_button import FilterButton
from assetdeck.ui.folder_tree import FolderTree
from assetdeck.ui.library_switcher import LibrarySwitcher
from assetdeck.ui.preview_popup import PreviewPopup
from assetdeck.ui.property_defs_dialog import PropertyDefsDialog
from assetdeck.ui.relocate_dialog import RelocateDialog
from assetdeck.ui.scan_worker import ScanController
from assetdeck.ui.smart_collection_panel import SmartCollectionPanel
from assetdeck.ui import icons, sidebar as sidebar_mod, theme
from assetdeck.ui.sidebar import Sidebar
from assetdeck.ui.status_led import StatusLed
from assetdeck.ui.tag_dialogs import QuickTagDialog
from assetdeck.ui.tag_tree import TagTree
from assetdeck.ui.categories import CATEGORIES
from assetdeck.ui.nav_history import NavHistory
from assetdeck.ui.category_bar import CategoryBar

log = logging.getLogger(__name__)

# Altura da faixa de cima (marca à esquerda, biblioteca e modo à direita).
# É a faixa INTEIRA que aparece na tela: desde a Fatia 95 o layout central
# não tem mais margem em cima, então não existe "meio espaço" fora dela.
ALTURA_FAIXA_TOPO = 42

# Paleta fixa do filtro de busca por cor (Fatia 39) — decisão do Rafael:
# botões de cor pré-definidos em vez de um seletor livre. Um hex
# representativo por balde; a tolerância de "quão perto conta" mora em
# assets_repo.COLOR_TOLERANCE, não aqui.
#
# Fatia 76: cada tom foi recentrado no MEIO da sua família de matiz, não num
# tom bonito qualquer. Isso importa desde que a comparação virou perceptual
# (ver `db/connection._color_distance`): o balde é uma fatia do círculo de
# cor em volta deste hex, então um verde puxado pro azul — era o caso do
# `#27ae60`, matiz 145° — deixava a folhagem real (matiz ~88°) fora do
# alcance. O verde agora está em 122°, no meio do caminho.
PALETA_CORES = [
    ("Cor: todas", None),
    ("Vermelho", "#c0392b"),     # ~6°
    ("Laranja", "#e67e22"),      # ~28°
    ("Amarelo", "#f1c40f"),      # ~48°
    ("Verde", "#43a047"),        # ~122° (era #27ae60, 145° — verde-esmeralda)
    ("Azul", "#2980b9"),         # ~204°
    ("Roxo", "#8e44ad"),         # ~282°
    ("Rosa", "#e84393"),         # ~330°
    ("Marrom", "#7f5539"),       # ~24°, escuro — separado do laranja pelo brilho
    ("Cinza", "#7f8c8d"),        # acromáticos: distinguidos por claro/escuro
    ("Branco", "#f5f5f5"),
    ("Preto", "#1a1a1a"),
]


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, library_root: str,
                 db_path: Path, thumbs_dir: Path) -> None:
        super().__init__()
        self._conn = conn  # conexão da thread da UI: SÓ leitura
        self._library_root = Path(library_root)
        # Biblioteca ATIVA (Fatia 69) — resolvida uma vez, usada pra
        # restringir grade/árvore de pastas/contagens a ela. Sem isso, um
        # banco com mais de uma biblioteca indexada (ex.: sobra de um
        # teste anterior nunca limpa) mistura os assets das duas.
        self._library_id = libraries_repo.get_or_create(conn, self._library_root)
        self._thumbs_dir = thumbs_dir
        self._db_path = db_path
        self._scan = ScanController(db_path, self._library_root, parent=self)
        self._pipeline = ThumbnailPipeline(thumbs_dir, parent=self)

        # Maximização (Fatia 94). `_maximizada_desejada` é o que veio do
        # config e vale só na primeira aparição; `_maximizada_reposta` faz a
        # reposição acontecer uma vez só, porque `showEvent` dispara toda vez
        # que a janela reaparece e depois da abertura quem manda é o Rafael.
        # `_maximizada` é o último valor VISTO ao vivo (o que se grava);
        # `_maximizada_desejada` é o que veio do config e vale só na primeira
        # aparição. Duas variáveis, e não uma, porque o gerenciador manda um
        # "não maximizada" logo que a janela aparece — com uma só, esse
        # evento apagava a intenção antes dela ser aplicada (medido).
        self._maximizada = False
        self._maximizada_desejada = False
        self._maximizada_reposta = False

        self.setWindowTitle("AssetDeck")
        self.resize(1280, 800)

        # --- busca + filtros ---
        # Fatia 66: a barra de busca saiu de uma faixa própria (ocupando a
        # linha inteira) e virou um campo compacto na linha de navegação,
        # do lado dos filtros (pedido do Rafael — "barra de pesquisa
        # enorme"). Largura fixa em vez de esticar; a dica de sintaxe (E/OU)
        # que cabia no placeholder virou tooltip, já que o campo encolheu.
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Buscar por nome…")
        self.search_box.setToolTip(
            "Buscar por nome — ex.: concreto, wood 4k, madeira E rústico, pedra OU metal"
        )
        self.search_box.setFixedWidth(220)
        self.search_box.setClearButtonEnabled(True)
        self._search_icon_action = self.search_box.addAction(
            icons.icon("search", theme.current_colors()["text_muted"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)  # espera parar de digitar
        self._search_debounce.timeout.connect(self._apply_filters)
        self.search_box.textChanged.connect(
            lambda _t: self._search_debounce.start()
        )

        self.categories = CategoryBar()
        self.categories.changed.connect(self._apply_filters)

        # Resolução mínima (Fatia 9) — era QComboBox longo ("Resolução: todas")
        # na barra de filtros; virou botão de ícone compacto na linha do
        # breadcrumb (pedido do Rafael, Fatia 28c). Filtro de nota mínima
        # removido na Fatia 62 (junto com a nota em si — só favorito ficou).
        self.res_filter = FilterButton(
            "resolution",
            [("Resolução: todas", None), ("≥ 1K", 1024), ("≥ 2K", 2048),
             ("≥ 4K", 4096), ("≥ 8K", 8192)],
        )
        self.res_filter.changed.connect(self._apply_filters)

        # Busca por cor dominante (Fatia 39) — cor média do arquivo
        # principal, comparada contra uma paleta fixa de botões.
        self.color_filter = FilterButton("palette", PALETA_CORES, swatch=True)
        self.color_filter.changed.connect(self._apply_filters)

        # Ordenação (Fatia 63) — mesmo padrão dos filtros acima: um botão
        # ícone-only com popup de escolha única. O valor é o par
        # (coluna, direção) direto, sem widget de direção separado — cada
        # opção do menu já é uma combinação completa e legível.
        self.sort_filter = FilterButton(
            "sort",
            [
                ("Nome (A→Z)", ("name", "asc")),
                ("Nome (Z→A)", ("name", "desc")),
                ("Modificado (mais recente)", ("modified", "desc")),
                ("Modificado (mais antigo)", ("modified", "asc")),
                ("Tamanho (maior)", ("size", "desc")),
                ("Tamanho (menor)", ("size", "asc")),
                ("Resolução (maior)", ("resolution", "desc")),
                ("Resolução (menor)", ("resolution", "asc")),
            ],
        )
        self.sort_filter.changed.connect(self._apply_filters)

        # fav_check/group_check/deps_check/hidden_check saíram daqui (Fatia
        # 43) — viram QAction marcável no menu Janela, junto dos toggles de
        # painel (_setup_window_menu). QAction tem isChecked()/setChecked()/
        # toggled igual QCheckBox, então nada que já lê esses 4 atributos
        # precisou mudar, só o tipo do widget.
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(140)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.setObjectName("primary")
        self.rescan_btn.setIcon(icons.icon("refresh", theme.current_colors()["on_accent"]))
        self.rescan_btn.clicked.connect(self.start_scan)

        # --- pastas + grid + detalhes ---
        self.model = AssetGridModel(conn, self._library_root, self._pipeline,
                                    library_id=self._library_id, parent=self)
        self.grid = AssetGridView()
        self.grid.setModel(self.model)
        self.grid.selectionModel().currentChanged.connect(self._on_selection)
        self.model.dataChanged.connect(self._on_data_changed)
        self.grid.image_dropped.connect(self._on_image_dropped)
        self.grid.asset_preview_dropped.connect(self._on_asset_preview_dropped)
        # Duplo clique = preview ampliado (NÃO abre o arquivo — pedido do
        # Rafael). `self.preview_popup` é criado mais abaixo, depois do
        # widget central existir (Fatia 65: overlay embutido, não janela
        # separada — precisa de um host com tamanho real pra caber dentro).
        self.grid.doubleClicked.connect(self._open_preview)
        # Menu de contexto: agrupar/desagrupar à mão
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._grid_menu)

        self.folders = FolderTree()
        self.folders.dir_selected.connect(self._on_dir_selected)
        self.folders.assets_dropped.connect(self._mover_assets)  # Fatia 85
        self.history = NavHistory()

        self.tags = TagTree()
        self.tags.tag_selected.connect(lambda _t: self._apply_filters())
        self.tags.assets_dropped.connect(self._on_assets_dropped)
        self.tags.structure_changed.connect(self._on_tags_structure_changed)

        self.collections = CollectionTree()
        self.collections.collection_selected.connect(lambda _c: self._apply_filters())
        self.collections.assets_dropped.connect(self._on_assets_dropped_to_collection)
        self.collections.structure_changed.connect(self._on_collections_structure_changed)

        self.smart_collections = SmartCollectionPanel()
        self.smart_collections.smart_selected.connect(self._on_smart_collection_selected)
        self.smart_collections.save_requested.connect(self._on_save_smart_collection)
        self.smart_collections.structure_changed.connect(
            lambda: self.smart_collections.reload(self._conn)
        )

        # Lateral (Fatia 45): rail de ícones + UM painel com as quatro seções,
        # cada uma com contador e recolhível pelo cabeçalho. Antes eram quatro
        # QFrame#card empilhados num splitter, todos do mesmo tamanho e sem
        # contador — não dava pra saber, olhando, o que tinha conteúdo.
        # O card em volta continua obrigatório pelo mesmo motivo da Fatia 24:
        # o viewport de uma QTreeWidget/QListView pinta retângulo no canto e
        # vaza por cima de qualquer border-radius posto nela diretamente.
        # Agora é um card só, envolvendo o splitter inteiro (ver ui/sidebar.py).
        self.sidebar = Sidebar([
            ("pastas", "Pastas", "nav-pastas", self.folders),
            ("tags", "Tags", "nav-tags", self.tags),
            ("colecoes", "Coleções", "nav-colecoes", self.collections),
            ("smart", "Smart Collections", "nav-smart", self.smart_collections),
        ])
        left = self.sidebar
        self._left_default_sizes = [280, 200, 200, 200]
        self.sidebar.splitter.setSizes(self._left_default_sizes)
        # O piso vem do próprio Sidebar (cabeçalho mais largo + rail); aqui só
        # o teto, que é escolha de proporção da janela.
        left.setMaximumWidth(340 + sidebar_mod.LARGURA_RAIL)
        # Segue exposto com o nome antigo: é o splitter DAS SEÇÕES, que
        # `_restaurar_layout` redimensiona e o teste de layout confere.
        self._left_splitter = self.sidebar.splitter

        # DetailsPanel é o próprio card (objectName="card" nele mesmo) — não
        # precisa de embrulho extra, então o min/max width fica nele direto.
        self.details = DetailsPanel(self._library_root)
        self.details.setMinimumWidth(300)
        self.details.setMaximumWidth(380)
        # SEM sombra (Fatia 76) — o Rafael viu "a sombra do painel de detalhes
        # parece estar vazando, tente deixar que nem no grid de assets". Era o
        # único dos três painéis com `apply_card_shadow`: a lateral e a grade
        # já usam `make_card(sombra=False)`. Um `QGraphicsDropShadowEffect`
        # desenha a sombra DENTRO do retângulo que o layout deu ao widget —
        # como o splitter entrega o espaço exato, ela não tem pra onde ir e
        # espalha por cima do próprio conteúdo, ainda por cima interagindo com
        # o `QScrollArea` de dentro. O contorno + a superfície do `#card` já
        # separam o painel do fundo, que é exatamente como a grade faz.
        self.details.notes_saved.connect(self._on_notes_saved)
        self.details.tag_toggled.connect(self._on_tag_toggled)
        self.details.starred_changed.connect(self._on_starred_changed)
        self.details.preview_add_requested.connect(self._on_preview_add)
        self.details.preview_cover_requested.connect(self._on_preview_cover)
        self.details.preview_remove_requested.connect(self._on_preview_remove)
        self.details.property_value_changed.connect(self._on_property_value_changed)
        self.details.manage_properties_requested.connect(self._manage_properties)
        self.details.aviso.connect(
            lambda recado: self.statusBar().showMessage(recado, 8000))
        self.details.check_textures_requested.connect(self._check_textures)

        # Caminho navegável acima da grade (Fatia 28, estilo Connecter): a
        # única pista de "onde estou" antes disso era o item selecionado na
        # árvore de pastas — fácil de perder de vista depois de rolar.
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("sectionTitle")

        # Escopo e contagem da faixa 3 (Fatia 46). Criados AQUI, antes do
        # `_update_breadcrumb("")` logo abaixo — ele já escreve no escopo, e
        # criá-los junto do layout (mais adiante) deixava a janela inteira
        # sem subir.
        self.list_scope = QLabel()
        self.list_scope.setObjectName("listScope")
        self.list_count = QLabel()
        self.list_count.setObjectName("listCount")

        self._update_breadcrumb("")

        # Slider de tamanho da miniatura (pedido do Rafael, estilo Connecter):
        # a grade e o modelo mudam JUNTOS — ver AssetGridView.set_icon_size.
        # Fatia 56: saiu do rodapé (longe da grade, alça "bola" destoando dos
        # botões de filtro ao lado) e foi pra faixa 3, junto de nota/
        # resolução/cor — mesma linha que já refina o que está na tela.
        # Mais estreito que os 110px de antes: cabe ao lado de 3 botões
        # ícone-only sem empurrar o contador pra fora.
        from PySide6.QtWidgets import QSlider

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(asset_grid.MIN_ICON, asset_grid.MAX_ICON)
        self.size_slider.setValue(asset_grid.DEFAULT_ICON)
        self.size_slider.setFixedWidth(72)
        self.size_slider.setToolTip("Tamanho das miniaturas")
        self.size_slider.valueChanged.connect(self.grid.set_icon_size)

        # Voltar / Avançar / Subir (Fatia 32): a árvore lateral era o único
        # jeito de mudar de pasta, sem como desfazer.
        self.back_btn = self._nav_button("arrow-left", "Voltar (Alt+←)",
                                         self._go_back)
        self.fwd_btn = self._nav_button("arrow-right", "Avançar (Alt+→)",
                                        self._go_forward)
        self.up_btn = self._nav_button("arrow-up", "Subir um nível (Alt+↑)",
                                       self._go_up)

        # Topo em DUAS faixas (Fatia 66, era três desde a Fatia 46). O
        # Rafael pediu pra parar de dedicar uma faixa própria só pra busca
        # ("barra de pesquisa enorme") — ela virou um campo compacto na
        # MESMA linha da navegação, junto dos filtros finos que já moravam
        # ali do lado (resolução/cor/ordenar/tamanho) e do botão de
        # reindexar (que tinha uma faixa só pra ele também). Mockup
        # aprovado por ele antes de mexer no código:
        #
        #   1. onde estou + refino     → setas + caminho + busca + filtros +
        #                                 tamanho + reindexar
        #   2. o que quero ver + conta → as 6 categorias + quantos itens
        #
        # A contagem ("N assets") desce pra linha das categorias — não tinha
        # mais faixa própria sobrando pra ela.
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        path_row.addWidget(self.back_btn)
        path_row.addWidget(self.fwd_btn)
        path_row.addWidget(self.up_btn)
        path_row.addSpacing(4)
        path_row.addWidget(self.breadcrumb, stretch=1)
        path_row.addWidget(self.search_box)
        path_row.addWidget(self.sort_filter)
        path_row.addWidget(self.res_filter)
        path_row.addWidget(self.color_filter)
        path_row.addSpacing(4)
        path_row.addWidget(self.size_slider)
        path_row.addSpacing(4)
        path_row.addWidget(self.progress)
        path_row.addWidget(self.rescan_btn)
        # objectName próprio: controles mais baixos SÓ nesta fileira
        # (padding menor) — pedido do Rafael de enxutar verticalmente,
        # herdado de quando só a busca morava aqui (Fatia 28d).
        path_row_widget = QWidget()
        path_row_widget.setObjectName("searchBar")
        path_row_widget.setLayout(path_row)

        category_row = QHBoxLayout()
        category_row.setContentsMargins(0, 0, 0, 0)
        category_row.addWidget(self.categories)
        category_row.addStretch(1)
        category_row.addWidget(self.list_scope)
        category_row.addWidget(self.list_count)

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)
        grid_layout.addWidget(path_row_widget)
        grid_layout.addWidget(self._breadcrumb_divider(horizontal=True))
        grid_layout.addLayout(category_row)
        grid_layout.addWidget(self.grid)

        # A grade NUNCA leva sombra: ela rola com centenas de assets, e o
        # QGraphicsDropShadowEffect força o Qt a renderizar a subárvore
        # inteira fora da tela a cada quadro (medido ~2,3x mais caro).
        grid_card = theme.make_card(grid_container, sombra=False)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.addWidget(left)
        splitter.addWidget(grid_card)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        # A lateral abre no próprio piso (rail + o cabeçalho mais largo). Antes
        # da Fatia 45 era 240 fixo — o rail sairia desse orçamento e o
        # cabeçalho "SMART COLLECTIONS" aparecia cortado.
        self._main_default_sizes = [self.sidebar.minimumWidth(), 740, 300]
        splitter.setSizes(self._main_default_sizes)
        self._main_splitter = splitter

        # A busca não tem mais faixa/card próprio (Fatia 66) — mora dentro
        # do `grid_card`, junto do resto da navegação. `central` agora só
        # empilha o splitter (painéis + grade + detalhes).
        central = QWidget()
        central.setObjectName("appSurface")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(central)
        # Sem margem em cima nem embaixo (Fatia 95): quem dá o respiro ali
        # agora é a altura da barra de menus e a do rodapé. Antes a folga era
        # metade margem, metade barra — e o conteúdo das duas barras ficava
        # centralizado só na METADE que é a barra, aparecendo acima do meio
        # do espaço que o Rafael enxerga. Foi o que ele descreveu duas vezes:
        # "deixe centralizado verticalmente no espaço em que está".
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self._central = central  # host dos overlays (preview, HDRI) — Fatia 65

        # Duplo clique num asset = preview ampliado, embutido na própria
        # janela (Fatia 65) — precisa do widget central já existir.
        self.preview_popup = PreviewPopup(self._central)

        # Navegação de pastas (Fatia 32), mesmas teclas de um navegador.
        # Ctrl+T (tags) virou QAction da Fatia 36 — ver _setup_menu_bar
        # (um QShortcut e uma QAction com a MESMA tecla no mesmo widget
        # geram "ambiguous shortcut" no Qt e nenhum dos dois dispara).
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence("Alt+Left"), self, activated=self._go_back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self._go_forward)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self._go_up)
        self._tag_clipboard: list[int] | None = None

        # Fatia 67: os 5 menus de topo (Arquivo/Editar/Ferramentas/
        # Configurações/Janela — Fatia 36) viraram uma janela única de
        # configurações, acessada por um ícone de engrenagem — pedido do
        # Rafael. `SettingsWindow` cria os botões/checkboxes e os atribui
        # DIRETO nesta MainWindow (`self.group_check`, `self.render_action`
        # etc.) — precisa vir depois de tudo que ela referencia já existir
        # (`self.sidebar`, `self.details`, `self.model`, `self.tags`).
        from assetdeck.ui.settings_window import SettingsWindow

        self.settings_window = SettingsWindow(self)
        # Ajuste pós-tela: engrenagem no pé do rail lateral (canto
        # inferior-esquerdo), não na barra de menus — pedido do Rafael.
        self.sidebar.rail.settings_clicked.connect(self._abrir_configuracoes)
        self._setup_atalhos_globais()
        self._setup_bridge()  # ponte com o Blender + RenderController (F2)
        self._setup_brand_bar()  # Fatia 50 — marca e contexto na mesma faixa

        # Contagem sempre visível no rodapé (Fatia 28) — antes vivia num
        # QLabel solto na barra de filtros, junto de mais 10 widgets.
        self.footer_count = QLabel()
        self.statusBar().addPermanentWidget(self.footer_count)

        # Tamanho da biblioteca (Fatia 49). O rodapé da referência que o
        # Rafael escolheu informa; o nosso só contava assets. Soma em `files`,
        # não em `assets`: um set PBR são vários arquivos.
        self.footer_size = QLabel()
        self.footer_size.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.footer_size)
        # Altura FIXA em vez de só um teto (Fatia 78, pedido do Rafael:
        # "deixe centralizado verticalmente nesse espaço em que está, além de
        # colocar margens maiores das bordas"). Com `setMaximumHeight` o Qt
        # encolhia a barra até o texto encostar em cima e embaixo; com altura
        # fixa sobra folga, e o respiro lateral vem do `padding` do
        # `QStatusBar` no QSS. Continua enxuto — só não espremido.
        # 46 = os 32 de antes + os 14 de margem que saíram do layout central
        # (ver `setContentsMargins` acima). O espaço embaixo é o mesmo de
        # sempre; a diferença é que agora ele pertence todo à barra, e o texto
        # cai no meio dele.
        self.statusBar().setFixedHeight(46)
        self.statusBar().setSizeGripEnabled(False)  # o canto pontilhado comia a margem direita
        # Margem lateral do rodapé (Fatia 78, "colocar margens maiores das
        # bordas"). Vale para os widgets permanentes da direita — contagem,
        # tamanho, LED do Blender —, que é onde mora a informação que fica.
        #
        # A MENSAGEM DA ESQUERDA não se move por aqui: o `QStatusBar` a
        # desenha ele mesmo no `paintEvent`, ignorando tanto o `padding` do
        # QSS quanto `contentsMargins` (as três formas foram medidas na tela:
        # o texto seguia a 7px da borda nas três). Movê-la exigiria trocar os
        # 45 `showMessage()` deste arquivo por um QLabel próprio — e mais 7
        # testes que leem `currentMessage()`. Não compensa por 11px, mas fica
        # registrado caso o Rafael queira.
        self.statusBar().layout().setContentsMargins(18, 0, 18, 0)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self._reload_all()
        # Precisa vir DEPOIS de `_reload_all()`: restaurar filtro/tag/pasta
        # exige pastas e tags já carregadas na árvore (Fatia 54).
        self._restore_ui_state()

    # ---- filtros e contagem ----

    def _reload_all(self, *, warmup: bool = True) -> None:
        """Recarga completa: pastas, tags, checklist de tipos e grid — E (se
        `warmup=True`) o pré-aquecimento de thumbnails da biblioteca inteira
        (`warmup_library`, não o `reload()` barato). Só é chamada depois de
        algo que pode ter trazido arquivo novo pra biblioteca (varredura,
        rename em lote, agrupar/desagrupar) — nunca a cada mudancinha, por
        isso pode pagar o custo do pré-aquecimento aqui sem travar a UI o
        tempo todo.

        `warmup=False` (Fatia 64): pula o pré-aquecimento — usado quando o
        Rafael reportou que a reindexação automática ao abrir "demora
        demais" e uma causa real era rodar esse pente-fino (medido na Fatia
        45: ~1,1s numa biblioteca de 23 mil assets, SÓ nisso) duas vezes
        seguidas sem necessidade — uma na abertura, outra de novo aqui
        depois do scan — mesmo quando o scan não trouxe NADA que precise de
        thumbnail nova (arquivo só sumiu, ou só voltou metadado de sidecar
        pra um arquivo que já tinha thumb). `_on_finished` decide qual caso
        é este. Pastas/tags/contagens continuam sempre atualizadas — só o
        `_warmup()` caro fica de fora.

        `folders.reload` reseta a seleção para a raiz — antes da Fatia 32
        isso jogava o Rafael de volta pra "tudo" no fim de cada varredura, e
        ainda deixava o breadcrumb mostrando a pasta antiga. Agora a pasta é
        restaurada (ou cai na raiz, se sumiu do disco)."""
        anterior = self.history.current()
        self.folders.reload(self._conn, library_id=self._library_id)
        self.tags.reload(self._conn)
        self.collections.reload(self._conn)
        self.smart_collections.reload(self._conn)
        self.categories.reload(self._conn, self._category_counts())
        if warmup:
            self.model.warmup_library()
        else:
            self.model.reload()
        self._go_to_dir(anterior, record=False)

    def _category_counts(self) -> dict:
        """Contagem por categoria respeitando os filtros ativos (menos o de
        categoria) — é o número que cada botão da barra exibe."""
        return assets_repo.count_by_category(
            self._conn, CATEGORIES, library_id=self._library_id,
            **self._current_filters_dict())

    def _current_filters_dict(self) -> dict:
        """O dicionário de filtros ativos — o mesmo que `list_for_grid`
        aceita. Usado para consultar a grid E para salvar uma Smart
        Collection (Fatia 18)."""
        current = self.folders.currentItem()
        dir_prefix = current.data(0, 32) if current else ""
        sort_by, sort_dir = self.sort_filter.value()
        return dict(
            search=self.search_box.text().strip(),
            category_filters=self.categories.selection(),
            dir_prefix=dir_prefix,
            # "Incluir subpastas" saiu da UI (pedido do Rafael, Fatia 28c —
            # ele não via caso de uso pra desligar). Sempre True agora.
            include_subdirs=True,
            tag_id=self.tags.current_tag_id(),
            starred_only=self.fav_check.isChecked(),
            min_resolution=self.res_filter.value(),
            include_hidden=self.hidden_check.isChecked(),
            include_dependencies=self.deps_check.isChecked(),
            include_missing=self.missing_check.isChecked(),
            collection_id=self.collections.current_collection_id(),
            dominant_color=self.color_filter.value(),
            sort_by=sort_by, sort_dir=sort_dir,
        )

    def _apply_filters(self) -> None:
        self.model.set_filters(**self._current_filters_dict())
        self.categories.update_counts(self._category_counts())
        self.refresh_count()

    def _update_breadcrumb(self, dir_prefix: str) -> None:
        """"" -> biblioteca inteira; "A/B" -> "Biblioteca › A › B"."""
        if not dir_prefix:
            self._breadcrumb_full = "BIBLIOTECA (TUDO)"
        else:
            trilha = " › ".join(dir_prefix.split("/"))
            self._breadcrumb_full = f"BIBLIOTECA › {trilha}".upper()
        self._elide_breadcrumb()
        # Escopo da faixa 3 (Fatia 46). O caminho na faixa 1 responde "onde
        # estou"; este responde "o que esta lista contém", que é diferente
        # assim que um filtro entra.
        self.list_scope.setText(
            "Toda a biblioteca" if not dir_prefix else "Nesta pasta")

    def _elide_breadcrumb(self) -> None:
        """A linha divide espaço com 3 botões de navegação, 6 de categoria,
        nota, resolução e o slider — caminho fundo não cabe. Corta pela
        ESQUERDA: a pasta atual (à direita) é o que importa saber."""
        from PySide6.QtGui import QFontMetrics

        fm = QFontMetrics(self.breadcrumb.font())
        largura = max(self.breadcrumb.width(), 80)
        self.breadcrumb.setText(
            fm.elidedText(self._breadcrumb_full, Qt.TextElideMode.ElideLeft, largura))
        self.breadcrumb.setToolTip(self._breadcrumb_full)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_breadcrumb_full"):  # pode disparar durante o __init__
            self._elide_breadcrumb()  # o espaço disponível mudou

    def _on_dir_selected(self, dir_prefix: str) -> None:
        """Clique na árvore: a árvore já mudou de seleção sozinha, só falta
        registrar no histórico e refiltar."""
        self.history.push(dir_prefix)
        self._update_breadcrumb(dir_prefix)
        self._apply_filters()
        self._sync_nav_buttons()

    # ---- navegação de pastas (Fatia 32) ----

    def _set_bridge_status(self, estado: str, texto: str) -> None:
        """LED e texto do Blender andam JUNTOS — um ponto verde ao lado de
        "porta ocupada" seria pior do que não ter LED nenhum."""
        self._bridge_led.set_estado(estado)
        self.bridge_status.setText(texto)

    def _breadcrumb_divider(self, *, horizontal: bool = False) -> QFrame:
        """Traço fino de 1px separando as faixas do topo.

        Nasceu vertical na Fatia 43 (separando grupos dentro de UMA linha).
        Na Fatia 46 o topo virou três faixas empilhadas, então o mesmo traço
        passou a ser usado deitado, entre elas — mesma cor, mesma espessura.
        """
        linha = QFrame()
        linha.setObjectName("breadcrumbDivider")
        if horizontal:
            linha.setFixedHeight(1)
        else:
            linha.setFixedWidth(1)
        return linha

    def _nav_button(self, icone: str, dica: str, slot) -> QToolButton:
        b = QToolButton()
        b.setObjectName("ghost")  # sem moldura (Fatia 43) — pedido do Rafael,
        # os botões de voltar/avançar/subir estavam pesados demais na tela
        b.setIcon(icons.icon(icone, theme.current_colors()["text_muted"]))
        b.setIconSize(QSize(16, 16))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setToolTip(dica)
        b.clicked.connect(slot)
        b.setEnabled(False)
        return b

    def _go_to_dir(self, dir_prefix: str, record: bool = True) -> None:
        """ÚNICO caminho para mudar de pasta programaticamente. Existia
        espalhado entre `_on_dir_selected` e `_restore_filters`; centralizar
        é o que mantém o histórico honesto."""
        if not self.folders.select(dir_prefix) and dir_prefix:
            # Pasta sumiu (reindexação, biblioteca trocada): cai na raiz em
            # vez de deixar a seleção velha com o breadcrumb mentindo.
            log.info("Pasta %r não existe mais — voltando para a raiz.", dir_prefix)
            self.folders.select("")
            dir_prefix = ""
            self.history.replace_current("")
        if record:
            self.history.push(dir_prefix)
        self._update_breadcrumb(dir_prefix)
        self._apply_filters()
        self._sync_nav_buttons()

    def _go_back(self) -> None:
        if self.history.can_back():
            self._go_to_dir(self.history.back(), record=False)

    def _go_forward(self) -> None:
        if self.history.can_forward():
            self._go_to_dir(self.history.forward(), record=False)

    def _go_up(self) -> None:
        atual = self.history.current()
        if atual:
            self._go_to_dir(atual.rsplit("/", 1)[0] if "/" in atual else "")

    def _sync_nav_buttons(self) -> None:
        self.back_btn.setEnabled(self.history.can_back())
        self.fwd_btn.setEnabled(self.history.can_forward())
        self.up_btn.setEnabled(bool(self.history.current()))

    def mousePressEvent(self, event) -> None:
        """Botões laterais do mouse navegam, como em qualquer navegador."""
        if event.button() == Qt.MouseButton.BackButton:
            self._go_back()
        elif event.button() == Qt.MouseButton.ForwardButton:
            self._go_forward()
        else:
            super().mousePressEvent(event)

    # ---- tags ----

    def _after_tags_changed(self, asset_ids: list[int], mensagem: str) -> None:
        """Rotina comum pós-mudança de tags: FTS, sidecars e refresh.

        BUG relatado pelo Rafael (2026-08-14): taggear "parecia não fazer
        nada" arrastando, pelo Ctrl+T ou pelo checkbox do painel de
        detalhes. A gravação no banco sempre funcionou (conferido direto
        com `tags_repo.assign`/`tags_of`) — o que faltava era a grid
        refletir a mudança: só chamava `_apply_filters()` quando havia
        filtro de tag ou busca ativos, então navegando uma pasta normal
        (o caso mais comum) nada na tela mudava. Antes da Fatia 61 isso já
        era um bug (silencioso, sem nenhum indício visual de tag na grid);
        o badge novo só expôs o sintoma. Mesmo padrão que `_on_starred_changed`
        já usava (nota em estrelas removida na Fatia 62): `_reload_grid()`
        sempre roda (barato, preserva rolagem/seleção — Fatia 45);
        `_apply_filters()` continua só quando o FILTRO ativo pode mudar de
        resultado (tag/busca).
        """
        assets_repo.rebuild_fts(self._conn)
        for aid in asset_ids:
            sidecar_writer.write_for_asset(self._conn, self._library_root, aid)
        if self.tags.current_tag_id() is not None or self.search_box.text().strip():
            self._apply_filters()  # o filtro ativo pode ter mudado de resultado
        else:
            self._reload_grid()  # sem filtro: só repinta os badges/estado dos cards
        self.statusBar().showMessage(mensagem)

    def _on_assets_dropped(self, tag_id: int, asset_ids: list[int]) -> None:
        for aid in asset_ids:
            tags_repo.assign(self._conn, aid, tag_id)
        nome = tags_repo.tag_path(self._conn, tag_id)
        self._after_tags_changed(
            asset_ids, f"{len(asset_ids)} asset(s) taggeados com '{nome}' (arrastar)"
        )

    def _on_tag_toggled(self, asset_id: int, tag_id: int, checked: bool) -> None:
        # Sugestão do Rafael: com N assets selecionados, o checkbox aplica a TODOS
        alvos = self._selected_asset_ids() or [asset_id]
        for aid in alvos:
            if checked:
                tags_repo.assign(self._conn, aid, tag_id)
            else:
                tags_repo.unassign(self._conn, aid, tag_id)
        nome = tags_repo.tag_path(self._conn, tag_id)
        sufixo = f" em {len(alvos)} assets" if len(alvos) > 1 else ""
        self._after_tags_changed(
            alvos,
            f"Tag '{nome}' {'adicionada' if checked else 'removida'}{sufixo}",
        )

    def _on_starred_changed(self, starred: bool) -> None:
        alvos = self._selected_asset_ids()
        if not alvos:
            return
        for aid in alvos:
            assets_repo.set_starred(self._conn, aid, starred)
            sidecar_writer.write_for_asset(self._conn, self._library_root, aid)
        self._reload_grid()
        sufixo = f" em {len(alvos)} assets" if len(alvos) > 1 else ""
        self.statusBar().showMessage(
            ("★ Favoritado" if starred else "Favorito removido") + sufixo
        )
        if self.fav_check.isChecked():
            self._apply_filters()

    def _on_tags_structure_changed(self) -> None:
        assets_repo.rebuild_fts(self._conn)
        self.tags.reload(self._conn)
        self._apply_filters()

    # ---- coleções manuais (Fatia 17) ----

    def _on_assets_dropped_to_collection(self, collection_id: int, asset_ids: list[int]) -> None:
        n = collections_repo.add_items(self._conn, collection_id, asset_ids)
        if self.collections.current_collection_id() == collection_id:
            self._apply_filters()  # a coleção aberta ganhou itens novos
        self.statusBar().showMessage(f"{n} asset(s) adicionados à coleção (arrastar)")

    def _on_collections_structure_changed(self) -> None:
        self.collections.reload(self._conn)
        self._apply_filters()

    def _remove_from_current_collection(self, asset_ids: list[int]) -> None:
        collection_id = self.collections.current_collection_id()
        if collection_id is None:
            return
        for aid in asset_ids:
            collections_repo.remove_item(self._conn, collection_id, aid)
        self._apply_filters()
        self.statusBar().showMessage(f"{len(asset_ids)} asset(s) removidos da coleção")

    # ---- barra de menus (Fatia 36, redistribuída na Fatia 67) ----

    def _setup_brand_bar(self) -> None:
        """Marca à esquerda e contexto à direita, NA MESMA faixa dos menus
        (que agora não têm mais nenhum QMenu de topo — Fatia 67 moveu
        Arquivo/Editar/Ferramentas/Configurações/Janela pra
        `SettingsWindow`).

        A engrenagem que abre a `SettingsWindow` NÃO mora aqui — ajuste
        pós-tela da Fatia 67: o Rafael pediu canto inferior-esquerdo em vez
        do canto da barra de menus, então ela vive no pé do
        `SidebarRail` (ver `sidebar.py`), perto de onde já ficavam os
        toggles de painel.

        O mockup escolhido pelo Rafael tinha aqui uma faixa com marca e abas
        (Biblioteca / Coleções / Duplicados). As abas foram descartadas
        conscientemente: elas não correspondem a telas do AssetDeck —
        Coleções é uma seção da lateral e Duplicados é um diálogo de
        Ferramentas. Abas que só abrissem diálogos prometeriam uma navegação
        que não existe. A marca e o contexto, que são o resto da faixa,
        entram sem esse problema.

        `setCornerWidget` é o único jeito de pôr widget numa QMenuBar sem
        substituí-la por uma barra própria — e substituí-la custaria perder
        atalho de teclado, navegação por Alt e integração com o gerenciador
        de janelas.
        """
        from PySide6.QtWidgets import QHBoxLayout

        barra = self.menuBar()
        # Mesma ideia do rodapé (Fatia 95): a faixa engole a margem que era do
        # layout central, então marca e seletor ficam no meio do espaço que
        # aparece na tela. 42 é MENOR que os 51 de antes (37 de barra + 14 de
        # margem) — o Rafael pediu pra diminuir o espaço superior.
        barra.setFixedHeight(ALTURA_FAIXA_TOPO)

        marca = QWidget()
        marca_layout = QHBoxLayout(marca)
        marca_layout.setContentsMargins(10, 0, 12, 0)
        marca_layout.setSpacing(7)
        ponto = QFrame()
        ponto.setObjectName("brandDot")
        ponto.setFixedSize(8, 8)
        rotulo = QLabel("AssetDeck")
        rotulo.setObjectName("brandName")
        marca_layout.addWidget(ponto)
        marca_layout.addWidget(rotulo)

        # A referência em `self` é OBRIGATÓRIA. A documentação do Qt diz que a
        # barra assume a posse do corner widget, mas o PySide não transfere a
        # posse aqui: sem uma referência do lado Python, `marca` é coletado
        # quando esta função retorna e o canto volta a ficar vazio. Medido —
        # o widget aparecia logo depois do `setCornerWidget` e sumia depois.
        self._brand_widget = marca
        barra.setCornerWidget(marca, Qt.Corner.TopLeftCorner)

        # À direita vai o que NÃO aparece em nenhum outro lugar da tela:
        # biblioteca ativa (Fatia 70: virou seletor de verdade — o banco
        # pode ter mais de uma registrada) e o modo (claro/escuro). A
        # contagem de assets, que o mockup punha aqui, já está no
        # cabeçalho da lista E no rodapé — um terceiro lugar seria ruído.
        contexto = QWidget()
        # Altura da FAIXA INTEIRA, não a do botão (Fatia 95b). O Qt encosta o
        # widget do canto DIREITO no topo da barra de menus — medido: ele
        # ficava em y=0..29 numa faixa de 42, com 13px sobrando só embaixo. E
        # como o widget tinha exatamente a altura do botão, o `AlignVCenter`
        # de dentro não tinha folga nenhuma pra distribuir: centralizava o
        # botão nele mesmo. Dando a altura da faixa ao widget, o alinhamento
        # interno passa a ter o que centralizar. (O canto ESQUERDO, com a
        # marca, o Qt já centraliza sozinho — as duas pontas não recebem o
        # mesmo tratamento.)
        contexto.setFixedHeight(ALTURA_FAIXA_TOPO)
        contexto_layout = QHBoxLayout(contexto)
        contexto_layout.setContentsMargins(0, 0, 12, 0)
        contexto_layout.setSpacing(2)
        self.library_switcher = LibrarySwitcher(self._conn, self._library_id)
        self.library_switcher.switch_requested.connect(self._on_switch_library)
        self.brand_context = QLabel()
        self.brand_context.setObjectName("brandContext")
        # AlignVCenter explícito (Fatia 78, pedido do Rafael: "deixe a parte
        # de trocar a biblioteca centralizada verticalmente nesse espaço").
        # Sem isso o QHBoxLayout ESTICA os dois na altura toda do canto da
        # barra de menus — a pastilha do seletor ficava alta demais e colada
        # nas bordas de cima e de baixo, em vez de boiar no meio.
        contexto_layout.addWidget(
            self.library_switcher, 0, Qt.AlignmentFlag.AlignVCenter)
        contexto_layout.addWidget(
            self.brand_context, 0, Qt.AlignmentFlag.AlignVCenter)

        # Mesmo motivo do `_brand_widget` acima: sem a referência em `self`,
        # o Python coleta `contexto` assim que a função retorna.
        self._contexto_widget = contexto
        self.statusBar()  # garante a barra criada antes do primeiro update
        barra.setCornerWidget(contexto, Qt.Corner.TopRightCorner)
        self._update_brand_context()

    def _update_brand_context(self) -> None:
        from assetdeck import config  # import local, como o resto do arquivo

        modo = "Escuro" if config.load_config().get("theme_mode") == "escuro" else "Claro"
        self.brand_context.setText(f"{modo}   ")

    def _on_switch_library(self, root_path: str) -> None:
        """Biblioteca escolhida no `LibrarySwitcher` (Fatia 70) — trocar de
        verdade exige reabrir o app: `library_root`/`library_id` são
        resolvidos uma vez em `app.py`, ANTES da `MainWindow` existir, e o
        `ScanController`/`ThumbnailPipeline`/modelo da grade são todos
        construídos em cima disso. Reconstruir tudo ao vivo é risco
        desproporcional ao ganho — fechar e abrir de novo já passa pelo
        fluxo normal de inicialização, sem precisar de nenhum código novo
        lá."""
        from PySide6.QtWidgets import QMessageBox

        from assetdeck import config

        nome = Path(root_path).name
        escolha = QMessageBox.question(
            self, "Trocar de biblioteca",
            f'Trocar a biblioteca ativa para "{nome}"?\n\n{root_path}\n\n'
            "O AssetDeck precisa fechar e abrir de novo pra aplicar — a "
            "próxima abertura reindexa essa pasta (pode demorar se ela "
            "for grande).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if escolha != QMessageBox.StandardButton.Yes:
            return

        cfg = config.load_config()
        cfg["library_root"] = root_path
        config.save_config(cfg)
        log.info("Biblioteca ativa trocada para %s — fechando pra aplicar.", root_path)
        self.close()

    def _setup_atalhos_globais(self) -> None:
        """Fatia 67: os 5 menus de topo viraram a janela de configurações
        (`SettingsWindow`), mas 3 atalhos de teclado precisam continuar
        funcionando em QUALQUER lugar do app, não só quando aquela janela
        está aberta — um atalho preso a um botão dentro dela só dispararia
        com ela em foco. `self.addAction(...)` registra o atalho na
        MAINWINDOW; sem um menu pra morar, a ação fica "invisível" de
        propósito (`Sair`/`Editar tags` já têm um lugar visível: o botão na
        janela de configurações e o menu de contexto da grade)."""
        from PySide6.QtGui import QAction, QKeySequence

        self.rescan_btn.setShortcut(QKeySequence("Ctrl+R"))

        tag_action = QAction(self)
        tag_action.setShortcut(QKeySequence("Ctrl+T"))
        tag_action.triggered.connect(self._quick_tag_dialog)
        self.addAction(tag_action)

        self.sair_action = QAction(self)
        self.sair_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.sair_action.triggered.connect(self.close)
        self.addAction(self.sair_action)

    def _abrir_configuracoes(self) -> None:
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _toggle_dark_mode(self, escuro: bool) -> None:
        from PySide6.QtWidgets import QApplication

        from assetdeck import config
        from assetdeck.ui import theme

        modo = "escuro" if escuro else "claro"
        theme.apply_theme(QApplication.instance(), theme.Variant(mode=modo))
        self._refresh_theme_dependent_widgets()
        cfg = config.load_config()
        cfg["theme_mode"] = modo
        config.save_config(cfg)
        self._update_brand_context()  # o canto direito da faixa diz o modo
        self.statusBar().showMessage(f"Modo {modo} aplicado.")

    def _refresh_theme_dependent_widgets(self) -> None:
        """Widgets que pintam cor "à mão" (fora do QSS) precisam ser
        avisados na hora de trocar de modo claro/escuro — o QSS/paleta do
        Qt já se atualiza sozinho com `apply_theme()`, mas um ícone
        pré-tingido ou um QBrush cacheado, não (Fatia 43)."""
        pal = theme.current_colors()

        self.grid.itemDelegate().refresh_theme()
        self.model.refresh_theme()
        self.grid.viewport().update()

        self.categories.refresh_theme()
        self.sort_filter.refresh_theme()
        self.res_filter.refresh_theme()
        self.color_filter.refresh_theme()
        self.details.refresh_theme()
        self.sidebar.refresh_theme()
        self._bridge_led.refresh_theme()
        self.library_switcher.refresh_theme()  # ícone tingido à mão (Fatia 77)
        self.settings_window.refresh_theme()   # ícones da lateral (Fatia 80)
        if getattr(self, "_visor_win", None) is not None:
            # Só se já existir: criar o visualizador aqui montaria um contexto
            # OpenGL só porque o Rafael trocou de modo claro/escuro.
            self._visor_win.refresh_theme()

        self._search_icon_action.setIcon(icons.icon("search", pal["text_muted"]))
        self.rescan_btn.setIcon(icons.icon("refresh", pal["on_accent"]))
        for botao, nome_icone in (
            (self.back_btn, "arrow-left"),
            (self.fwd_btn, "arrow-right"),
            (self.up_btn, "arrow-up"),
        ):
            botao.setIcon(icons.icon(nome_icone, pal["text_muted"]))

    def _on_secao_alternada_pelo_rail(self, chave: str, visivel: bool) -> None:
        """Rail → checkbox da janela de configurações (Fatia 67, era o menu
        Janela). `blockSignals` evita o laço de volta (o checkbox chamaria
        `set_section_visible`, que remarcaria o rail)."""
        acao = self._acoes_por_secao.get(chave)
        if acao is None:
            log.error("Seção '%s' alternada pelo rail não tem checkbox correspondente.", chave)
            return
        acao.blockSignals(True)
        acao.setChecked(visivel)
        acao.blockSignals(False)

    def _restaurar_layout(self) -> None:
        # Mostra os widgets DIRETO (não só via `setChecked(True)`): se o
        # painel tivesse sido ocultado por outro caminho que não o próprio
        # toggle, a ação já estaria "checked" e setChecked(True) seria
        # no-op — sem emitir `toggled`, o painel continuaria escondido.
        self.details.setVisible(True)
        for chave, _rotulo in self._secoes_do_menu:
            self.sidebar.set_section_visible(chave, True)
            # Recolhida é estado independente de escondida: uma seção visível
            # mas fechada continuaria só com a linha do título depois de
            # "restaurar layout", que não é restaurar nada.
            secao = self.sidebar.section_widget(chave)
            if secao is not None:
                secao.set_collapsed(False)
        for acao in self._window_menu_actions:
            acao.setChecked(True)
        self._left_splitter.setSizes(self._left_default_sizes)
        self._main_splitter.setSizes(self._main_default_sizes)
        self.statusBar().showMessage("Layout restaurado ao padrão")

    # ---- ações do menu Editar que dependem da seleção da grid ----

    def _copy_tags_selected(self) -> None:
        ids = self._selected_asset_ids()
        if len(ids) != 1:
            self.statusBar().showMessage("Selecione exatamente 1 asset para copiar as tags.")
            return
        self._copy_tags(ids[0])

    def _paste_tags_selected(self, replace: bool) -> None:
        ids = self._selected_asset_ids()
        if not ids:
            self.statusBar().showMessage("Selecione ao menos 1 asset antes de colar tags.")
            return
        if not self._tag_clipboard:
            self.statusBar().showMessage("Nenhuma tag copiada ainda.")
            return
        self._paste_tags(ids, replace=replace)

    def _batch_rename_dos_selecionados(self) -> None:
        ids = self._selected_asset_ids()
        if not ids:
            self.statusBar().showMessage("Selecione ao menos 1 asset para renomear em lote.")
            return
        self._batch_rename_selected(ids)

    # ---- preferências (Fatia 36) ----

    def _open_preferences(self) -> None:
        from assetdeck.ui.preferences_dialog import PreferencesDialog

        dlg = PreferencesDialog(self)
        if dlg.exec():
            self.statusBar().showMessage(
                "Preferências salvas — porta/ativação da ponte com o Blender "
                "só valem depois de reabrir o AssetDeck"
            )

    def _abrir_pasta_config(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from assetdeck import config

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.config_dir())))

    def _abrir_pasta_logs(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from assetdeck import config

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.logs_dir())))

    def _mover_assets(self, asset_ids: list, destino: str) -> None:
        """Assets arrastados da grade pra uma pasta da árvore (Fatia 85).

        Esta é a segunda operação do app que ESCREVE na biblioteca (a
        primeira é o batch rename). Por isso o caminho é: planejar sem
        tocar em disco → mostrar exatamente o que vai acontecer → só então
        mover. O Rafael vê a conta antes, não depois.
        """
        from PySide6.QtWidgets import QMessageBox

        from assetdeck import mover
        from assetdeck.ui.details_panel import human_size

        plano = mover.planejar(self._conn, self._library_id, self._library_root,
                               [int(i) for i in asset_ids], destino)

        onde = destino or "a raiz da biblioteca"
        if not plano.mover:
            # Nada a fazer: explica POR QUE, item a item. "Não deu" sem
            # motivo é o tipo de mensagem que faz o Rafael abrir o log.
            detalhe = "\n".join(f"• {r.nome}: {r.motivo}" for r in plano.recusar)
            QMessageBox.information(
                self, "Nada para mover",
                f"Nenhum dos assets selecionados pode ir para {onde}.\n\n{detalhe}")
            return

        linhas = [f"• {m.nome}  ({m.arquivos} arquivo(s))" for m in plano.mover[:12]]
        if len(plano.mover) > 12:
            linhas.append(f"…e mais {len(plano.mover) - 12}")
        texto = (
            f"Mover {len(plano.mover)} asset(s) para {onde}?\n\n"
            + "\n".join(linhas)
            + f"\n\nTotal: {plano.total_arquivos} arquivos, "
              f"{human_size(plano.total_bytes)}.\n"
              "A pasta de cada asset vai inteira — texturas e previews junto."
        )
        if plano.recusar:
            texto += f"\n\n{len(plano.recusar)} asset(s) ficam onde estão:\n"
            texto += "\n".join(f"• {r.nome}: {r.motivo}" for r in plano.recusar[:6])

        escolha = QMessageBox.question(
            self, "Mover assets", texto,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,   # padrão é NÃO mexer
        )
        if escolha != QMessageBox.StandardButton.Yes:
            log.info("Mover assets cancelado pelo Rafael.")
            return

        movidos, falhas = mover.executar(self._conn, self._library_id,
                                         self._library_root, plano)
        # `warmup=False` (Fatia 89): mover NÃO traz arquivo novo pra
        # biblioteca — são os mesmos arquivos em outro lugar, e a miniatura é
        # indexada por `content_hash`, não por caminho, então continua
        # valendo. Com o padrão `warmup=True` cada arrasto pagava o
        # pente-fino de ~127 mil itens (medido na Fatia 88: 1,9s de UI
        # congelada) sem ter o que descobrir. É exatamente o caso que a
        # docstring de `_reload_all` descreve.
        self._reload_all(warmup=False)
        recado = f"{movidos} asset(s) movidos para {onde}"
        if falhas:
            recado += f" — {falhas} falharam (ver log)"
        self.statusBar().showMessage(recado)

    def _relocate_lost_assets(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from assetdeck.db.repos import libraries as libraries_repo

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        candidatos = relocator.find_candidates(self._conn, lib_id)
        if not candidatos:
            QMessageBox.information(
                self, "Nada para religar",
                "Nenhum arquivo sumido bate com um arquivo encontrado em outro "
                "lugar da biblioteca (mesmo conteúdo).",
            )
            return

        dlg = RelocateDialog(candidatos, self)
        if not dlg.exec():
            return

        pares = dlg.selected_pairs()
        religados = 0
        for missing_file_id, found_file_id in pares:
            keeper_id = relocator.relocate(self._conn, missing_file_id, found_file_id)
            if keeper_id is not None:
                sidecar_writer.write_for_asset(self._conn, self._library_root, keeper_id)
                religados += 1

        self._reload_all()
        self.statusBar().showMessage(f"{religados} asset(s) religados ao novo caminho")

    # ---- duplicados por conteúdo visual (Fatia 20) ----

    def _find_duplicates(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from assetdeck.db.repos import libraries as libraries_repo

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        grupos = duplicates_finder.find_duplicate_groups(self._conn, lib_id)
        if not grupos:
            QMessageBox.information(
                self, "Nada encontrado",
                "Nenhum grupo de assets com o mesmo conteúdo visual (phash) "
                "foi encontrado.",
            )
            return

        dlg = DuplicatesDialog(grupos, self)
        if not dlg.exec():
            return

        ids = dlg.selected_asset_ids()
        for aid in ids:
            assets_repo.set_hidden(self._conn, aid, True)

        self._reload_grid()
        self.statusBar().showMessage(
            f"{len(ids)} asset(s) duplicado(s) ocultado(s) da grade "
            "('Mostrar ocultos' traz de volta)"
        )

    # ---- batch rename (Fatia 23) — a única exceção ao somente-leitura ----

    def _batch_rename_selected(self, asset_ids: list[int]) -> None:
        from assetdeck.db.repos import libraries as libraries_repo

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        dlg = BatchRenameDialog(self._conn, lib_id, asset_ids, self)
        if not dlg.exec():
            return

        plano = dlg.get_plan()
        if not plano:
            return
        sucesso, falhas = batch_rename.apply_plan(self._conn, self._library_root, plano)
        self._reload_all()
        recado = f"{sucesso} arquivo(s) renomeado(s)"
        if falhas:
            recado += f" · {falhas} falharam (ver log)"
        self.statusBar().showMessage(recado)

    # ---- coleções inteligentes / buscas salvas (Fatia 18) ----

    def _on_save_smart_collection(self, nome: str) -> None:
        smart_collections_repo.create(self._conn, nome, self._current_filters_dict())
        self.smart_collections.reload(self._conn)
        self.statusBar().showMessage(f"Coleção inteligente '{nome}' salva")

    def _on_smart_collection_selected(self, smart_id) -> None:
        if smart_id is None:
            # "(nenhuma aplicada)" — volta os filtros pro padrão (mostra
            # tudo), em vez de deixar o que estava marcado antes parado ali
            self._restore_filters({})
            self.statusBar().showMessage("Filtros voltaram ao padrão")
            return
        registro = smart_collections_repo.get(self._conn, smart_id)
        if registro is None:
            return
        self._restore_filters(registro["query"])
        self.statusBar().showMessage(f"Coleção inteligente '{registro['name']}' aplicada")

    def _restore_filters(self, query: dict) -> None:
        """Reescreve os widgets de filtro a partir de uma query salva e
        reaplica — a partir daí, a reatividade que já existe (nota, tags,
        reindexação) mantém a visão sempre recalculada.

        `include_subdirs` de uma Smart Collection antiga (salva antes da
        Fatia 28c) é ignorado — o toggle saiu da UI, agora é sempre True."""
        self.search_box.setText(query.get("search") or "")
        if query.get("category_filters"):
            self.categories.set_selection(query["category_filters"])
        else:
            # Salva antes da Fatia 31: só tinha `asset_types` crus.
            self.categories.set_selection_from_types(query.get("asset_types") or [])
        self.fav_check.setChecked(bool(query.get("starred_only")))
        self.res_filter.set_value(query.get("min_resolution"))
        self.color_filter.set_value(query.get("dominant_color"))
        # Sem valor salvo (query de antes da Fatia 63): cai no padrão do
        # próprio FilterButton, que é a primeira opção — nome A→Z.
        self.sort_filter.set_value(
            (query.get("sort_by", "name"), query.get("sort_dir", "asc"))
        )
        self.hidden_check.setChecked(bool(query.get("include_hidden")))
        self.deps_check.setChecked(bool(query.get("include_dependencies")))
        self.missing_check.setChecked(bool(query.get("include_missing")))
        self.tags.select(query.get("tag_id"))
        self.collections.select(query.get("collection_id"))
        # Por último: `_go_to_dir` já reaplica os filtros com tudo no lugar,
        # e registra a pasta no histórico (decisão do Rafael — aplicar uma
        # Smart Collection é navegação como qualquer outra).
        self._go_to_dir(query.get("dir_prefix") or "")

    def _selected_asset_ids(self) -> list[int]:
        rows = [self.model.row_at(i)
                for i in self.grid.selectionModel().selectedIndexes()]
        return sorted({r["id"] for r in rows if r is not None})

    def _quick_tag_dialog(self) -> None:
        ids = self._selected_asset_ids()
        if not ids:
            self.statusBar().showMessage("Selecione asset(s) antes do Ctrl+T.")
            return
        dlg = QuickTagDialog(self._conn, ids, self)
        if dlg.exec():
            mudancas = dlg.apply()
            if mudancas:
                self._after_tags_changed(
                    ids, f"Tags atualizadas em {len(ids)} asset(s)"
                )
                self._refresh_details_tags()

    def _refresh_details_tags(self) -> None:
        self._on_selection(self.grid.currentIndex(), QModelIndex())

    # ---- custom properties (Fatia 22) ----

    def _on_property_value_changed(self, asset_id: int, property_id: int, value) -> None:
        properties_repo.set_value(self._conn, asset_id, property_id, value)
        sidecar_writer.write_for_asset(self._conn, self._library_root, asset_id)
        self.statusBar().showMessage("Propriedade salva")

    def _manage_properties(self) -> None:
        dlg = PropertyDefsDialog(self._conn, self)
        dlg.exec()
        if dlg.changed:
            self._refresh_details_tags()  # recarrega o painel (inclui propriedades)

    # ---- texturas faltando de um .blend (Fatia 40) ----

    def _check_textures(self, _asset_id: int, caminho: str) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        from assetdeck.blender.missing_textures import list_missing_textures
        from assetdeck.blender.render import blender_command
        from assetdeck.ui.missing_textures_dialog import MissingTexturesDialog

        if blender_command() is None:
            QMessageBox.warning(
                self, "Blender não encontrado",
                "Não achei o Blender nesta máquina. Instale-o (blender.org "
                "ou 'flatpak install flathub org.blender.Blender') e garanta "
                "que o comando 'blender' esteja no PATH.",
            )
            return

        # Ação sob demanda de 1 asset, alguns segundos — cursor de espera
        # em vez da infraestrutura de fila/progresso da Fatia 38 (só vale
        # a pena pra job em lote pela biblioteca inteira).
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            resultado = list_missing_textures(Path(caminho))
        finally:
            QApplication.restoreOverrideCursor()

        if not resultado.ok:
            QMessageBox.warning(self, "Checagem falhou", resultado.erro)
            return
        if not resultado.perdidas:
            recado = "Nenhuma textura faltando."
            if resultado.recuperadas_auto:
                recado += (f" ({resultado.recuperadas_auto} estavam com caminho "
                          "quebrado, mas foram religadas automaticamente.)")
            QMessageBox.information(self, "Texturas em ordem", recado)
            return

        dlg = MissingTexturesDialog(Path(caminho), resultado.perdidas,
                                    resultado.recuperadas_auto, self)
        dlg.exec()

    # ---- notas / sidecar ----

    def _on_notes_saved(self, asset_id: int, texto: str) -> None:
        assets_repo.set_notes(self._conn, asset_id, texto)
        dest = sidecar_writer.write_for_asset(self._conn, self._library_root, asset_id)
        if dest is not None:
            self.statusBar().showMessage(f"Nota salva e espelhada em {dest.name}")
        else:
            self.statusBar().showMessage(
                "Nota salva no banco; sidecar adiado (arquivo sumido — ver log)"
            )

    def _reload_grid(self) -> None:
        """Recarrega a grid PRESERVANDO rolagem e seleção.

        Sem isso, anexar um preview jogava a lista de volta ao topo e o
        Rafael tinha que rolar tudo de novo a cada asset.
        """
        barra = self.grid.verticalScrollBar()
        posicao = barra.value()
        atual = self.model.row_at(self.grid.currentIndex())
        asset_id = atual["id"] if atual else None

        self.model.reload()

        if asset_id is not None:
            idx = self.model.index_of_asset(asset_id)
            if idx is not None:
                # setCurrentIndex ROLA a view até o item — por isso a barra
                # é reposta depois, nunca antes.
                self.grid.setCurrentIndex(idx)
        barra.setValue(min(posicao, barra.maximum()))

    def refresh_count(self) -> int:
        total = assets_repo.count_active(self._conn, library_id=self._library_id)
        shown = self.model.rowCount()
        texto = f"{total} assets" if shown == total else f"{shown} de {total} assets"
        selecionados = len(self._selected_asset_ids())
        if selecionados > 1:
            texto += f" · {selecionados} selecionados"

        # Sumido some da grade, mas NUNCA em silêncio (Fatia 100). A
        # biblioteca do Rafael mora num disco externo: se ele não montar, a
        # varredura marca tudo como sumido, e sem este aviso ele abriria o
        # app com a grade vazia e nenhuma explicação.
        if not self.missing_check.isChecked():
            sumidos = assets_repo.count_missing(self._conn,
                                                library_id=self._library_id)
            if sumidos:
                texto += f" · {sumidos} sumidos"
        self.footer_count.setText(texto)

        # O mesmo número aparece de propósito no cabeçalho da lista: o rodapé
        # é periférico (o olho não está lá quando se mexe num filtro), e a
        # faixa 3 fica logo acima da grade, ao lado dos controles que acabaram
        # de mudar esse número. Aqui é só o que está VISÍVEL — o total e a
        # seleção continuam sendo assunto do rodapé.
        self.list_count.setText(f"{shown} assets")

        # O tamanho não muda a cada filtro (é a biblioteca inteira), mas
        # recalcular aqui é barato — um SUM indexado — e garante que ele
        # acompanhe uma reindexação sem precisar de um gancho próprio.
        from assetdeck.ui.details_panel import human_size

        self.footer_size.setText(
            human_size(assets_repo.total_bytes(self._conn, library_id=self._library_id)))
        return total

    # ---- seleção / detalhes ----

    def _thumb_from_disk(self, row) -> "QPixmap | None":
        """Thumb em alta resolução para o preview grande do painel de
        detalhes (a cópia em RAM do modelo da grade está reduzida para caber
        na célula — ampliá-la ficaria borrada).

        Bug corrigido: uma capa CUSTOMIZADA (arrastar uma imagem sobre um
        modelo, Fatia 10b) nunca passava por `thumbs_dir` — ela mora em
        `previews_dir()`, via `cover_path`. Este método nunca olhava para
        `cover_path`, então caía direto no fallback de RAM, que também usava
        uma chave de cache desatualizada (sem o `:{ICON}` da Fatia 27) — a
        combinação fazia o preview grande nunca aparecer para esses assets.
        """
        from PySide6.QtGui import QPixmap

        from assetdeck.thumbs.cache import thumb_path

        cover = row.get("cover_path")
        if cover:
            pix = QPixmap(cover)
            return pix if not pix.isNull() else None

        p = thumb_path(self._thumbs_dir, row["content_hash"])
        if p.exists():
            pix = QPixmap(str(p))
            if not pix.isNull():
                return pix
        return QPixmapCache.find(f"thumb:{row['content_hash']}:{asset_grid.ICON}")

    def _on_selection(self, current: QModelIndex, _previous: QModelIndex) -> None:
        row = self.model.row_at(current)
        if row is not None:
            self.details.show_asset(row, self._thumb_from_disk(row))
            self.details.load_starred(bool(row["starred"]))
            self.details.load_tags(
                tags_repo.list_tree(self._conn),
                {t["id"] for t in tags_repo.tags_of(self._conn, row["id"])},
            )
            self.details.set_multi_count(len(self._selected_asset_ids()))
            self.details.load_gallery(previews_repo.list_for(self._conn, row["id"]))
            self.details.load_properties(
                properties_repo.list_defs(self._conn),
                properties_repo.get_values_for_asset(self._conn, row["id"]),
            )

    def _on_data_changed(self, top_left: QModelIndex, _br, _roles) -> None:
        # Se a thumb que acabou de ficar pronta é a do asset selecionado,
        # atualiza o preview grande do painel.
        if top_left == self.grid.currentIndex():
            self._on_selection(top_left, QModelIndex())

    # ---- preview ampliado e agrupamento manual ----

    def _open_preview(self, index: QModelIndex) -> None:
        row = self.model.row_at(index)
        if row is None:
            return
        caminho = Path(self._library_root) / row["rel_path"]
        if can_hdr(caminho):
            # HDRI achatado num QLabel não deixa avaliar a luz (Fatia 34).
            log.info("Duplo clique: abrindo o visualizador de HDRI para %s",
                     caminho.name)
            self._visualizador().abrir_hdri(caminho)
            return
        if caminho.suffix.lower() in model3d_loader.EXTENSOES_SUPORTADAS:
            # Fase 6: modelo com câmera orbitando em vez do preview
            # achatado. content_hash só é usado pelo loader de .blend
            # (cache da exportação via Blender) — o resto ignora.
            log.info("Duplo clique: abrindo o visualizador de modelo para %s",
                     caminho.name)
            self._visualizador().abrir_modelo(caminho, row["content_hash"])
            return
        maps = None
        if row["asset_type"] == "pbr_set" and self.group_check.isChecked():
            # PBR Material Viewer: botões para alternar entre os mapas do set
            maps = assets_repo.list_files(self._conn, row["id"])
        self.preview_popup.show_for(row, self._library_root,
                                    self._thumb_from_disk(row), maps=maps)

    def _visualizador(self):
        """Janela dos visualizadores 3D (HDRI e modelo na mesma casca desde
        a Fatia 90), criada sob demanda: o contexto OpenGL só é montado se o
        Rafael realmente abrir um — quem nunca abre não paga nada.

        Janela PRÓPRIA, não overlay embutido: um `QOpenGLWidget` dentro da
        MainWindow muda o modo de composição da JANELA INTEIRA do AssetDeck
        na primeira vez que aparece, e o app todo pisca (tentado e revertido
        na Fatia 65 — ver a docstring de `ui/viewer_window.py`)."""
        if getattr(self, "_visor_win", None) is None:
            from assetdeck.ui.viewer_window import VisualizadorWindow

            self._visor_win = VisualizadorWindow(self)
        return self._visor_win

    def prewarm_gl_viewers(self) -> None:
        """Mostra e esconde a janela dos visualizadores uma vez, fora da
        tela, na abertura do app — `AA_ShareOpenGLContexts` (`app.py`)
        não bastou (Rafael confirmou na tela: o piscar continua na
        PRIMEIRA vez que uma janela de OpenGL aparece na sessão, some da
        segunda em diante). A troca de modo de composição da janela é
        por JANELA DE TOPO, na primeira vez que ela ganha um
        `QOpenGLWidget` — fazer isso acontecer aqui, escondido, evita que
        aconteça na hora que ele abrir o primeiro HDRI/modelo de verdade.

        Mover pra fora da tela (não só esconder) importa: `hide()` sem
        nunca ter aparecido não garante que o Qt chegou a pintar um
        frame — e é o PAINT que dispara a negociação da superfície.
        """
        from PySide6.QtWidgets import QApplication

        # O ESTADO da janela principal (maximizada/normal) tem de sobreviver
        # a isto (Fatia 83). O visualizador é janela de topo FILHA desta;
        # mostrar e esconder ela fazia o Qt recalcular o estado
        # do pai e deixá-lo em "normal" — só o ESTADO, o tamanho continuava o
        # de maximizada. O resultado na tela: uma janela do tamanho da tela
        # que o gerenciador considera normal, então o botão de maximizar
        # "maximiza" pro mesmo tamanho e nada acontece. Foi como o Rafael
        # relatou: "não consigo mais maximizar a janela".
        estado_antes = self.windowState()

        # UMA janela desde a Fatia 90 (as duas superfícies de GL vivem num
        # `QStackedWidget` dela). A transição de composição é por JANELA DE
        # TOPO, então juntar as duas cortou metade deste custo — que é o
        # trecho mais caro da abertura depois da árvore de pastas.
        # `WA_DontShowOnScreen` (Fatia 93): o Qt monta a janela e PINTA um
        # frame — que é o que dispara a troca de composição, o motivo deste
        # método existir — sem nunca entregá-la ao gerenciador de janelas.
        #
        # Antes daqui saía um `move(-10000, -10000)` + `show()` + `hide()`.
        # Isso deixava o visualizador ABRINDO MINIMIZADO pro resto da sessão:
        # desmapear uma janela no X a marca como "iconificada" (é o que
        # `hide()` faz), e o gerenciador reaplica esse estado toda vez que ela
        # reaparece. Medido nos dois sentidos na tela do Rafael: com este
        # pré-aquecimento nascia minimizada, sem ele nascia normal — e não era
        # por estar fora da tela (a versão invisível por opacidade, na mesma
        # posição, minimizava igual). Era o par mapear/desmapear.
        visor = self._visualizador()
        visor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        visor.show()
        QApplication.processEvents()
        visor.hide()
        visor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)

        if self.windowState() != estado_antes:
            self.setWindowState(estado_antes)

    def _grid_menu(self, pos) -> None:
        selecionados = [
            self.model.row_at(i) for i in self.grid.selectionModel().selectedIndexes()
        ]
        selecionados = [r for r in selecionados if r is not None]
        if not selecionados:
            return
        menu = self._montar_menu_grid(selecionados)
        menu.exec(self.grid.mapToGlobal(pos))

    def _montar_menu_grid(self, selecionados: list[dict]):
        """Monta o menu de contexto da grade SEM executá-lo.

        Separado de `_grid_menu` (Fatia 101) porque `QMenu.exec()` é
        bloqueante e, sendo um método do Qt em C++, não dá pra interceptar
        por monkeypatch em teste (tentado — o processo trava esperando um
        evento de fechamento que nunca chega, mesmo offscreen). Com o menu
        MONTADO como valor de retorno, o teste inspeciona as ações sem
        precisar abrir nada de verdade.
        """
        from PySide6.QtWidgets import QMenu

        ids = sorted({r["id"] for r in selecionados})
        menu = QMenu(self)

        # Tags: copiar/colar/substituir (funciona em qualquer visão)
        menu.addAction("Editar tags…  (Ctrl+T)", self._quick_tag_dialog)
        if len(ids) == 1:
            menu.addAction("Copiar tags", lambda: self._copy_tags(ids[0]))
        if self._tag_clipboard is not None:
            n = len(self._tag_clipboard)
            menu.addAction(f"Colar tags (adicionar {n})",
                           lambda: self._paste_tags(ids, replace=False))
            menu.addAction(f"Substituir tags (colar {n} por cima)",
                           lambda: self._paste_tags(ids, replace=True))

        # Reexibir assets ocultos
        ocultos = [r for r in selecionados if r.get("hidden")]
        if ocultos:
            menu.addAction(
                f"Reexibir {len(ocultos)} oculto(s)",
                lambda: self._unhide([r["id"] for r in ocultos]),
            )

        # Coleções: tirar da coleção aberta no momento
        if self.collections.current_collection_id() is not None:
            menu.addAction(
                f"Remover da coleção atual ({len(ids)})",
                lambda: self._remove_from_current_collection(ids),
            )

        # Gerar capa (Fatia 101, pedido do Rafael: "gerar preview porém
        # somente de alguns assets"). Candidato = modelo .blend, presente no
        # disco, sem capa hoje — os mesmos três critérios de
        # `models_without_cover`, checados aqui em cima dos dados que a
        # grade JÁ tem (evita uma consulta extra só pra decidir se o item de
        # menu aparece). A ação some quando ninguém qualifica, em vez de
        # aparecer desabilitada sem dizer por quê.
        sem_capa = [
            r for r in selecionados
            if r["asset_type"] in ("model", "scene")
            and r["rel_path"].lower().endswith(".blend")
            and not r["cover_path"]
            and r["missing_since"] is None
        ]
        if sem_capa:
            menu.addSeparator()
            n = len(sem_capa)
            rotulo = f"Gerar capa ({n})…" if n > 1 else "Gerar capa…"
            menu.addAction(
                rotulo,
                lambda: self._render_covers([r["id"] for r in sem_capa]),
            )

        # Batch rename (Fatia 23) — a única exceção ao somente-leitura
        menu.addSeparator()
        menu.addAction("Renomear em lote…", lambda: self._batch_rename_selected(ids))

        # Agrupamento: só na visão agrupada
        if self.group_check.isChecked():
            menu.addSeparator()
            if len(selecionados) >= 2:
                act = menu.addAction(f"Agrupar {len(selecionados)} assets como um set")
                act.triggered.connect(lambda: self._group_selected(selecionados))
            atual = selecionados[0]
            if len(selecionados) == 1 and atual["files_count"] > 1:
                act = menu.addAction(f"Desagrupar ({atual['files_count']} arquivos)")
                act.triggered.connect(lambda: self._ungroup(atual))
        return menu

    def _unhide(self, asset_ids: list[int]) -> None:
        for aid in asset_ids:
            assets_repo.set_hidden(self._conn, aid, False)
        self._reload_grid()
        self.statusBar().showMessage(f"{len(asset_ids)} asset(s) reexibidos")

    def _copy_tags(self, asset_id: int) -> None:
        self._tag_clipboard = [t["id"] for t in tags_repo.tags_of(self._conn, asset_id)]
        self.statusBar().showMessage(f"{len(self._tag_clipboard)} tag(s) copiadas")

    def _paste_tags(self, asset_ids: list[int], replace: bool) -> None:
        if not self._tag_clipboard:
            return
        for aid in asset_ids:
            tags_repo.set_tags(self._conn, aid, self._tag_clipboard, replace=replace)
        verbo = "substituídas" if replace else "coladas"
        self._after_tags_changed(asset_ids, f"Tags {verbo} em {len(asset_ids)} asset(s)")
        self._refresh_details_tags()

    def _group_selected(self, rows) -> None:
        keeper = assets_repo.group_manual(self._conn, [r["id"] for r in rows])
        if keeper is not None:
            sidecar_writer.write_for_asset(self._conn, self._library_root, keeper)
            self._reload_all()
            self.statusBar().showMessage(
                f"{len(rows)} assets agrupados à mão (travado contra reagrupamento)"
            )

    def _ungroup(self, row) -> None:
        n = assets_repo.ungroup(self._conn, row["id"])
        if n:
            self._reload_all()
            self.statusBar().showMessage(
                f"Set desfeito em {n} assets (travados: o agrupador não refaz)"
            )

    # ---- ponte com o Blender (F2) ----

    def _setup_bridge(self) -> None:
        """Fatia 67: os botões de "Blender" (instalar add-on, gerar/parar
        capas, como usar) saíram do submenu "Ferramentas" pra página
        própria da `SettingsWindow`. Aqui sobra só o setup de verdade: o
        servidor da ponte e o `RenderController`."""
        from assetdeck import config
        from assetdeck.bridge.server import BridgeServer
        from assetdeck.ui.render_worker import RenderController

        # LED + texto (Fatia 49). Só o texto ("Blender: ouvindo :45017") exige
        # ler para saber se está tudo bem; o ponto colorido responde de
        # relance, que é o que se quer de um rodapé.
        self._bridge_led = StatusLed()
        self.statusBar().addPermanentWidget(self._bridge_led)
        self.bridge_status = QLabel()
        self.statusBar().addPermanentWidget(self.bridge_status)

        # RenderController roda o Blender headless por conta própria — não
        # depende da ponte estar ligada. Bug achado nesta fatia ao mover os
        # botões pra cá: antes, `self._render` só nascia DEPOIS do "return"
        # de baixo, então desligar a ponte desligava sem querer a geração
        # de capas também (o botão só existia dentro do submenu "Blender",
        # que só era montado se a ponte estivesse ativa) — agora que o
        # botão sempre existe (página própria), criar `self._render`
        # incondicionalmente é obrigatório, não só desejável.
        self._render = RenderController(
            self._db_path, self._library_root, config.previews_dir(), parent=self
        )

        cfg = config.load_config()
        self._bridge = None
        if not cfg.get("bridge_enabled", True):
            self._set_bridge_status("inativo", "Blender: ponte desligada")
            return

        token = config.ensure_bridge_token(cfg)
        porta = int(cfg.get("bridge_port", 45017))
        self._bridge = BridgeServer(self._conn, self._library_root, token,
                                    thumbs_dir=self._thumbs_dir, parent=self)
        if self._bridge.start(porta):
            self._set_bridge_status("atencao", f"Blender: ouvindo :{self._bridge.port}")
        else:
            self._set_bridge_status("erro", "Blender: porta ocupada (ver log)")
        # Ouvindo é ÂMBAR, conectado é VERDE: "ouvindo" quer dizer que a ponte
        # subiu mas o Blender ainda não falou com ela — pintar isso de verde
        # faria o rodapé afirmar uma conexão que não existe.
        self._bridge.client_connected.connect(
            lambda: self._set_bridge_status("ok", "Blender: conectado")
        )
        self._bridge.client_disconnected.connect(
            lambda: self._set_bridge_status(
                "atencao", f"Blender: ouvindo :{self._bridge.port}")
        )
        # O Blender salvou algo novo na biblioteca → reindexar
        self._bridge.rescan_requested.connect(self.start_scan)

    # ---- render de capas em lote ----

    def _start_render(self) -> None:
        """Botão "Renderizar…" de Configurações — SEM parâmetro extra de
        propósito: é o `clicked` de um `QPushButton` que chama isto direto
        (`settings_window.py`), e o Qt casaria um primeiro parâmetro
        posicional com o `bool` do sinal, não com uma lista de ids."""
        self._render_covers(None)

    def _render_covers(self, asset_ids: list[int] | None) -> None:
        """Gera capa dos modelos `.blend` sem capa — todos (`None`, o botão
        de Configurações) ou só o SUBCONJUNTO selecionado na grade (Fatia
        101, pedido do Rafael: "gerar preview porém somente de alguns
        assets", via botão direito)."""
        from PySide6.QtWidgets import QMessageBox

        from assetdeck.blender.render import blender_command, models_without_cover
        from assetdeck.db.repos import libraries as libraries_repo

        if self._render.running:
            QMessageBox.information(
                self, "Já tem um render em andamento",
                "Espere a fila atual terminar (ou clique em Parar) antes de "
                "pedir outra.",
            )
            return
        if blender_command() is None:
            QMessageBox.warning(
                self, "Blender não encontrado",
                "Não achei o Blender nesta máquina. Instale-o (blender.org "
                "ou 'flatpak install flathub org.blender.Blender') e garanta "
                "que o comando 'blender' esteja no PATH.",
            )
            return

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        pendentes = models_without_cover(self._conn, lib_id, self._library_root,
                                         asset_ids=asset_ids)
        if not pendentes:
            recado = ("Nenhum dos assets selecionados é modelo .blend sem "
                      "capa." if asset_ids is not None else
                      "Todos os modelos .blend já têm capa.")
            QMessageBox.information(self, "Nada a fazer", recado)
            return

        if asset_ids is not None:
            pergunta = (
                f"{len(pendentes)} modelo(s) selecionado(s) sem capa serão "
                "renderizados pelo Blender, um por vez, em segundo "
                "plano.\n\nComeçar?"
            )
        else:
            pergunta = (
                f"{len(pendentes)} modelo(s) sem capa serão renderizados pelo "
                "Blender, um por vez, em segundo plano.\n\n"
                "Leva alguns segundos por modelo e você pode continuar usando o "
                "AssetDeck normalmente. Começar?"
            )
        resposta = QMessageBox.question(self, "Gerar capas dos modelos", pergunta)
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.render_action.setEnabled(False)
        self.cancel_render_action.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(pendentes))
        self._render.start(self._on_render_progress, self._on_render_finished,
                           self._on_render_failed, asset_ids=asset_ids)

    def _stop_render(self) -> None:
        self._render.shutdown()
        self.statusBar().showMessage("Geração de capas interrompida.")
        self._reset_render_ui()

    def _reset_render_ui(self) -> None:
        self.render_action.setEnabled(True)
        self.cancel_render_action.setEnabled(False)
        self.progress.setVisible(False)

    def _on_render_progress(self, feitos: int, total: int, nome: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(feitos)
        self.statusBar().showMessage(f"Renderizando capa {feitos}/{total}: {nome}")

    def _on_render_finished(self, ok: int, falhas: int) -> None:
        self._reset_render_ui()
        self._reload_grid()
        recado = f"Capas geradas: {ok}"
        if falhas:
            recado += f" · {falhas} falharam (ver log)"
        self.statusBar().showMessage(recado)
        log.info("Render em lote concluído: %d ok, %d falhas.", ok, falhas)

    def _on_render_failed(self, mensagem: str) -> None:
        self._reset_render_ui()
        self.statusBar().showMessage(f"ERRO no render: {mensagem} (ver log)")

    def _install_addon(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from assetdeck import config
        from assetdeck.bridge import installer

        cfg = config.load_config()
        try:
            destinos = installer.install(
                config.ensure_bridge_token(cfg), int(cfg.get("bridge_port", 45017))
            )
        except (RuntimeError, OSError) as exc:
            log.exception("Instalação do add-on falhou")
            QMessageBox.warning(self, "Não consegui instalar o add-on", str(exc))
            return

        onde = "\n".join(str(d) for d in destinos)
        QMessageBox.information(
            self, "Add-on instalado",
            "Add-on copiado para:\n\n" + onde +
            "\n\nAgora, no Blender:\n"
            "1. Edit → Preferences → Add-ons\n"
            "2. Busque por 'AssetDeck' e marque a caixinha\n"
            "3. Na viewport 3D, aperte N e escolha a aba 'AssetDeck'\n\n"
            "Se o Blender já estava aberto, reinicie-o.",
        )

    def _bridge_help(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        porta = self._bridge.port if self._bridge and self._bridge.listening else "—"
        QMessageBox.information(
            self, "Ponte com o Blender",
            f"O AssetDeck escuta em 127.0.0.1:{porta} (apenas nesta máquina, "
            "com token — nada sai do seu computador).\n\n"
            "No Blender: aperte N na viewport 3D → aba 'AssetDeck' → "
            "'Conectar / Atualizar'.\n\n"
            "O AssetDeck precisa estar ABERTO para o add-on funcionar.",
        )

    # ---- previews customizados (Fatia 10) ----

    def _on_image_dropped(self, asset_id: int, path: str) -> None:
        """Imagem externa solta sobre um card vira a capa do asset."""
        from assetdeck import config

        try:
            previews_repo.add(self._conn, asset_id, Path(path), config.previews_dir())
        except (FileNotFoundError, OSError) as exc:
            log.exception("Falha ao adicionar preview")
            self.statusBar().showMessage(f"Não consegui usar essa imagem: {exc}")
            return
        self._reload_grid()
        self._refresh_details_tags()
        self.statusBar().showMessage("Preview definido como capa (imagem copiada — "
                                     "seu arquivo original não é tocado)")

    def _on_asset_preview_dropped(self, target_id: int, source_ids: list) -> None:
        """Asset de imagem arrastado de dentro da grid sobre outro asset
        (Fatia 10b — inicialmente só modelos; pedido do Rafael para valer em
        qualquer tipo sem preview de verdade: .ies, .psd, .cube, .dwg…).

        A regra não é mais por TIPO fixo — é por o alvo já ter ou não uma
        miniatura de verdade (`can_preview` no arquivo dele). Um .blend nunca
        tem; um .ies/.psd/.cube também não; um .svg agora tem (Fatia 28d), e
        um .jpg sempre teve — esses continuam de fora, a capa automática já
        é a imagem real."""
        from assetdeck import config
        from assetdeck.thumbs.preview import can_preview

        # Diagnóstico do bug relatado: se ESTE log não aparecer depois de um
        # dropEvent que emitiu asset_preview_dropped, o sinal se perdeu entre
        # a view e a janela — improvável (é uma conexão direta), mas descarta.
        log.info("_on_asset_preview_dropped: alvo=%s origem=%s", target_id, source_ids)

        alvo = self._conn.execute(
            "SELECT name, asset_type FROM assets WHERE id = ?", (target_id,)
        ).fetchone()
        if alvo is None:
            log.info("_on_asset_preview_dropped: alvo %s não existe no banco", target_id)
            return
        alvo_path = assets_repo.primary_abs_path(self._conn, target_id, self._library_root)
        if alvo_path is not None and can_preview(alvo_path):
            log.info("_on_asset_preview_dropped: '%s' já tem miniatura nativa (%s) — recusado",
                     alvo["name"], alvo_path)
            self.statusBar().showMessage(
                f"'{alvo['name']}' já tem uma miniatura de verdade — "
                "preview manual só vale para assets sem preview nativo"
            )
            return

        aplicados: list[int] = []
        falhas: list[str] = []
        for sid in source_ids:
            origem = assets_repo.primary_abs_path(self._conn, sid, self._library_root)
            if origem is None or not can_preview(origem):
                log.info("Origem %d ignorada (sumida ou sem preview visual).", sid)
                continue
            # `can_preview` só olha a EXTENSÃO — não confere se o arquivo
            # existe de verdade. Se `library_root` estiver errado (ou o
            # arquivo tiver sumido sem reindexar), previews_repo.add()
            # levanta FileNotFoundError. Sem este try/except o erro
            # desaparecia: a exceção nasce DENTRO de um sinal Qt emitido a
            # partir de startDrag() (chamado pelo C++ do Qt), e o Python
            # não tem chance de logar nada — bug real achado em 2026-08-05
            # ao investigar por que o fallback "funcionava" no log mas o
            # preview não aparecia. Nenhum except silencioso: sempre loga
            # com contexto (regra do projeto).
            try:
                previews_repo.add(self._conn, target_id, origem, config.previews_dir())
            except (FileNotFoundError, OSError) as exc:
                log.exception(
                    "Falha ao copiar preview do asset %d para %d (origem=%s, "
                    "library_root=%s)", sid, target_id, origem, self._library_root,
                )
                falhas.append(str(exc))
                continue
            aplicados.append(sid)
        if not aplicados:
            if falhas:
                self.statusBar().showMessage(
                    f"Falha ao copiar a imagem de origem: {falhas[0]} "
                    "(confira se a biblioteca está no caminho certo — ver log)"
                )
            else:
                self.statusBar().showMessage(
                    "Nenhuma das origens era uma imagem utilizável como preview."
                )
            return

        # Ocultar as imagens de origem? (pergunta, com memória da escolha)
        cfg = config.load_config()
        pref = cfg.get("hide_preview_source", "ask")
        if pref == "ask":
            from PySide6.QtWidgets import QCheckBox as _QCheck, QMessageBox

            box = QMessageBox(self)
            box.setWindowTitle("Ocultar preview de origem?")
            box.setText(
                f"A(s) imagem(ns) agora são preview de '{alvo['name']}'.\n"
                f"Deseja OCULTÁ-la(s) da grade? (reversível em 'Mostrar ocultos')"
            )
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            lembrar = _QCheck("Não perguntar de novo (lembrar esta escolha)")
            box.setCheckBox(lembrar)
            esconder = box.exec() == QMessageBox.StandardButton.Yes
            if lembrar.isChecked():
                cfg["hide_preview_source"] = "always" if esconder else "never"
                config.save_config(cfg)
        else:
            esconder = pref == "always"

        if esconder:
            for sid in aplicados:
                assets_repo.set_hidden(self._conn, sid, True)

        self._reload_grid()
        self._refresh_details_tags()
        sufixo = " (origens ocultadas)" if esconder else ""
        self.statusBar().showMessage(
            f"Preview de '{alvo['name']}' definido a partir de "
            f"{len(aplicados)} asset(s){sufixo}"
        )

    def _on_preview_add(self, asset_id: int) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _f = QFileDialog.getOpenFileName(
            self, "Escolher imagem de preview", str(Path.home()),
            "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp *.tga *.gif)",
        )
        if path:
            self._on_image_dropped(asset_id, path)

    def _on_preview_cover(self, preview_id: int) -> None:
        previews_repo.set_cover(self._conn, preview_id)
        self._reload_grid()
        self._refresh_details_tags()
        self.statusBar().showMessage("Capa atualizada")

    def _on_preview_remove(self, preview_id: int) -> None:
        previews_repo.soft_delete(self._conn, preview_id)
        self._reload_grid()
        self._refresh_details_tags()
        self.statusBar().showMessage("Preview removido da galeria")

    def _esquecer_assets_sumidos(self) -> None:
        """Manutenção → tira da grade, de vez, os assets 100% sumidos
        (Fatia 100 — pedido do Rafael depois de mover uma leva grande de
        assets Cosmos pra fora da biblioteca).

        A varredura sozinha NUNCA faz isso — só marca `missing_since` e
        deixa visível/filtrável, proteção contra HD desconectado por
        engano (SCHEMA.md). Esta é uma ação explícita, com confirmação
        mostrando o número exato antes de agir. Soft delete: reversível
        no banco, nunca mexe no disco.
        """
        from PySide6.QtWidgets import QMessageBox

        from assetdeck.db.repos import libraries as libraries_repo

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        n = assets_repo.count_missing_all(self._conn, lib_id)
        if not n:
            QMessageBox.information(
                self, "Nada a fazer",
                "Nenhum asset está totalmente sumido no momento.",
            )
            return

        resposta = QMessageBox.question(
            self, "Esquecer assets sumidos",
            f"{n} asset(s) têm TODOS os arquivos sumidos do caminho "
            "esperado (você os moveu ou apagou fora do AssetDeck).\n\n"
            "Eles vão sumir da grade e da busca. Os arquivos no disco, "
            "onde quer que estejam agora, não são tocados — isto só "
            "arruma o que o AssetDeck mostra. Continuar?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        marcados = assets_repo.purge_missing(self._conn, lib_id)
        self._reload_all()
        self.statusBar().showMessage(
            f"{marcados} asset(s) sumido(s) removido(s) da grade"
        )

    def _assinalar_previews_automaticamente(self) -> None:
        """Ferramentas → roda o casamento por nome igual (Fatia 57) sob
        demanda, sem esperar a próxima varredura — útil logo depois de
        ligar o toggle em Preferências, ou pra rever depois de arrumar
        nomes de arquivo na biblioteca."""
        from assetdeck import config
        from assetdeck.db.repos import libraries as libraries_repo
        from assetdeck.indexer.dependencies import attach_stem_match_previews

        cfg = config.load_config()
        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        criadas = attach_stem_match_previews(
            self._conn, lib_id, self._library_root, config.previews_dir(),
            hide_source=bool(cfg.get("auto_match_hide_source")),
        )
        if criadas:
            self._reload_grid()
            self._refresh_details_tags()
            self.statusBar().showMessage(
                f"{criadas} modelo(s) ganharam preview automático por nome igual"
            )
        else:
            self.statusBar().showMessage(
                "Nenhum modelo sem capa casou com uma imagem de mesmo nome"
            )

    # ---- varredura ----

    def start_scan(self) -> None:
        if self._scan.running:
            return
        self.rescan_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Indexando biblioteca…")
        self._scan.start(self._on_progress, self._on_finished, self._on_failed)

    def _on_progress(self, done: int, total: int, live_count: int) -> None:
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.footer_count.setText(f"{live_count} assets")
        self.statusBar().showMessage(f"Indexando… {done}/{total} arquivos")

    def _on_finished(self, stats: ScanStats) -> None:
        self.progress.setVisible(False)
        self.rescan_btn.setEnabled(True)
        # Fatia 64: só `added`/`updated`/`reappeared`/`grouped_sets` podem
        # trazer conteúdo visual NOVO (arquivo que nunca teve thumbnail, ou
        # cujo conteúdo mudou) — só esses justificam pagar o pré-aquecimento
        # caro de novo. `missing` (arquivo sumiu, nada novo pra desenhar) e
        # `restored` (metadado de sidecar voltou pra um arquivo que já
        # estava indexado e já tinha thumbnail) não precisam.
        precisa_thumb_nova = bool(
            stats.added or stats.updated or stats.reappeared or stats.grouped_sets
        )
        precisa_atualizar_algo = bool(
            precisa_thumb_nova or stats.missing or stats.restored
        )
        if precisa_atualizar_algo:
            # Mensagem ANTES da recarga (que pode travar a UI por um
            # instante) — sem isso a barra de status ficava com o texto de
            # "Indexando… X/Y arquivos" congelado durante o freeze, dando a
            # impressão de app travado. `processEvents()` força o repaint
            # AGORA — sem ele o Qt só pintaria depois que este método
            # (síncrono) terminasse, tarde demais pra servir de feedback.
            self.statusBar().showMessage("Sincronizando biblioteca…")
            QApplication.processEvents()
            self._reload_all(warmup=precisa_thumb_nova)
        else:
            self.refresh_count()
        self.statusBar().showMessage(f"Indexação concluída: {stats.summary()}")
        log.info("UI: indexação concluída — %s", stats.summary())

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.rescan_btn.setEnabled(True)
        self.statusBar().showMessage(f"ERRO na indexação: {message} (detalhes no log)")
        log.error("UI: indexação falhou — %s", message)

    # ---- estado de tela entre sessões (Fatia 54) ----

    def _chaves_dos_paineis(self) -> list[str]:
        """Mesma ordem de `_panel_toggles`/`_window_menu_actions`: a chave
        interna de cada seção da lateral, e `"detalhes"` pro painel que não
        é seção (não tem chave própria no Sidebar)."""
        return [chave for chave, _r in self._secoes_do_menu] + ["detalhes"]

    # ---- maximização: guardar e repor (Fatia 94) ----

    def changeEvent(self, event) -> None:  # noqa: N802
        """Anota a maximização enquanto ela ainda é verdade.

        Ler `isMaximized()` na hora de salvar NÃO funciona: dentro do
        `closeEvent` o estado já se foi — medido, a janela estava maximizada
        um instante antes e o config saía com `false`. Aqui o valor é anotado
        toda vez que MUDA, com a janela visível, que é quando ele vale.

        Minimizar não conta: quem minimiza uma janela maximizada quer ela
        maximizada de volta, não "normal".
        """
        from PySide6.QtCore import QEvent

        if (event.type() == QEvent.Type.WindowStateChange
                and self.isVisible() and not self.isMinimized()):
            self._maximizada = self.isMaximized()
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        """Repõe a maximização depois que a janela aparece.

        Não dá pra fazer isso no construtor junto com o `restoreGeometry`:
        no GNOME Shell o pedido de maximizar só vale DEPOIS que a janela foi
        mapeada — feito antes, é descartado sem aviso nenhum. Medido na tela
        do Rafael: `showMaximized()` junto do `show()` deixa a janela em
        800x500; 50ms depois, funciona.
        """
        super().showEvent(event)
        if self._maximizada_desejada and not self._maximizada_reposta:
            self._maximizada_reposta = True
            self._repor_maximizada()

    def _repor_maximizada(self, tentativa: int = 0) -> None:
        """Insiste na maximização até ela PEGAR, por cerca de 1,5s.

        Duas coisas medidas na tela do Rafael (GNOME Shell) explicam esta
        forma:

        1. O pedido feito antes da janela ser mapeada é descartado sem aviso
           — `showMaximized()` junto do `show()` deixa a janela em 800x500,
           50ms depois funciona. Por isso a reposição começa no `showEvent`.
        2. Pior: o que o `restoreGeometry` marca ANTES do mapa faz o Qt dizer
           `isMaximized() == True` na hora do `showEvent`, e o gerenciador
           desfaz logo depois. Uma verificação única cai nessa: ela vê
           "já está maximizada", desiste, e a janela abre normal.

        Daí conferir repetidamente por um intervalo, reafirmando sempre que
        não estiver maximizada, em vez de apostar num instante certo.
        """
        from PySide6.QtCore import QTimer

        # Insiste pelo INTERVALO INTEIRO, sem sair mais cedo (Fatia 97).
        #
        # A Fatia 94 tinha posto aqui uma saída antecipada: "duas leituras
        # seguidas dizendo maximizada, pode parar". Isso reintroduziu o
        # próprio defeito que este laço existe pra atravessar — o Qt responde
        # "sim, maximizada" logo depois do `restoreGeometry`, ANTES de o
        # gerenciador confirmar, e o gerenciador desfaz depois. Duas leituras
        # desse falso positivo bastavam pra desistir, e a janela abria em
        # tamanho normal. O Rafael relatou: "o programa voltou a não iniciar
        # maximizado".
        #
        # Pior: pus a saída antecipada DEPOIS de rodar o teste de ida e volta
        # que provava a correção, e não repeti o teste. Custa ~10 verificações
        # de nada em 1,5s; não vale economizar isso.
        if not self.isMaximized():
            self.showMaximized()
        if tentativa >= 10:
            if not self.isMaximized():
                log.warning("O gerenciador de janelas não aceitou maximizar "
                            "a janela — ela abre em tamanho normal.")
            return
        QTimer.singleShot(150, lambda: self._repor_maximizada(tentativa + 1))

    def _save_ui_state(self) -> None:
        """Grava geometria, painéis, splitters, tamanho do slider, tags
        expandidas e filtros ativos — tudo que o Rafael deixou arrumado
        na tela, pra próxima abertura vir do mesmo jeito."""
        from base64 import b64encode

        from assetdeck import config

        cfg = config.load_config()
        cfg["ui_state"] = {
            "window_geometry_b64": b64encode(bytes(self.saveGeometry())).decode("ascii"),
            # Bandeira PRÓPRIA, além do que o `saveGeometry` carrega (Fatia
            # 94). O Rafael: "a janela não vem maximizada (parece que não
            # guarda o estado anterior da sessão)". O que o `saveGeometry`
            # grava depende de `windowState()` valer no instante do
            # fechamento — e no GNOME esse estado some antes. Guardar à parte
            # o último valor VISTO durante a sessão (ver `changeEvent`) não
            # depende de quando o app é fechado.
            "window_maximized": self._maximizada,
            "left_splitter_sizes": self._left_splitter.sizes(),
            "main_splitter_sizes": self._main_splitter.sizes(),
            "panels_visible": dict(zip(
                self._chaves_dos_paineis(),
                (acao.isChecked() for acao in self._window_menu_actions),
            )),
            "icon_size": self.size_slider.value(),
            "tag_tree_expanded_ids": sorted(self.tags._tags_expandidas()),
            # Seções do painel de detalhes abertas/fechadas (Fatia 79) —
            # fechar uma seção só ajuda se ela continuar fechada amanhã.
            "details_sections": self.details.secoes_expandidas(),
            "filters": self._current_filters_dict(),
        }
        config.save_config(cfg)
        log.info("Estado da UI salvo (Fatia 54).")

    def _restore_ui_state(self) -> None:
        """Contrapartida de `_save_ui_state()`. Um `config.json` sem
        `ui_state` (primeira vez depois desta fatia, ou config antigo) faz
        nada — a janela abre com os padrões hardcoded de sempre."""
        from base64 import b64decode

        from assetdeck import config

        estado = config.load_config().get("ui_state") or {}
        if not estado:
            return

        geo_b64 = estado.get("window_geometry_b64")
        if geo_b64:
            self.restoreGeometry(b64decode(geo_b64))
        # Aplicado só depois que a janela aparece — ver `showEvent`. Pedir
        # maximização aqui, com a janela ainda não mapeada, é descartado em
        # silêncio pelo GNOME (medido: `showMaximized()` antes do mapa deixa
        # a janela em 800x500; 50ms depois, funciona).
        self._maximizada_desejada = bool(estado.get("window_maximized"))

        paineis = estado.get("panels_visible") or {}
        for chave, acao in zip(self._chaves_dos_paineis(), self._window_menu_actions):
            if chave in paineis:
                acao.setChecked(bool(paineis[chave]))

        # DEPOIS da visibilidade: esconder/mostrar um painel redistribui o
        # splitter sozinho, e o tamanho salvo é quem tem a última palavra.
        tam_esq = estado.get("left_splitter_sizes")
        if tam_esq:
            self._left_splitter.setSizes(tam_esq)
        tam_main = estado.get("main_splitter_sizes")
        if tam_main:
            self._main_splitter.setSizes(tam_main)

        icon_size = estado.get("icon_size")
        if icon_size:
            self.size_slider.setValue(int(icon_size))  # dispara set_icon_size

        # `is not None`, não truthy: lista VAZIA (nada expandido) é um
        # estado válido e tem de recolher tudo, não ser ignorada.
        expandidas = estado.get("tag_tree_expanded_ids")
        if expandidas is not None:
            self.tags.set_expanded(set(expandidas))

        secoes = estado.get("details_sections")
        if secoes:
            self.details.restaurar_secoes(secoes)

        filtros = estado.get("filters")
        if filtros:
            self._restore_filters(filtros)

    # ---- encerramento limpo ----

    def closeEvent(self, event) -> None:  # noqa: N802 (nome vem do Qt)
        self._save_ui_state()
        self._scan.shutdown()
        self._pipeline.shutdown()
        if getattr(self, "_bridge", None) is not None:
            self._bridge.stop()
        if getattr(self, "_render", None) is not None:
            self._render.shutdown()
        super().closeEvent(event)
