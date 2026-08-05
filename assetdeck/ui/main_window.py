"""Janela principal: grid de thumbnails + painel de detalhes + indexação."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (
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
from assetdeck.db.repos import previews as previews_repo
from assetdeck.db.repos import properties as properties_repo
from assetdeck.db.repos import smart_collections as smart_collections_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer import duplicates as duplicates_finder
from assetdeck.indexer import relocator
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

# Paleta fixa do filtro de busca por cor (Fatia 39) — decisão do Rafael:
# botões de cor pré-definidos em vez de um seletor livre. Um hex
# representativo por balde; a tolerância de "quão perto conta" mora em
# assets_repo.COLOR_TOLERANCE, não aqui.
PALETA_CORES = [
    ("Cor: todas", None),
    ("Vermelho", "#c0392b"),
    ("Laranja", "#e67e22"),
    ("Amarelo", "#f1c40f"),
    ("Verde", "#27ae60"),
    ("Azul", "#2980b9"),
    ("Roxo", "#8e44ad"),
    ("Rosa", "#e84393"),
    ("Marrom", "#7f5539"),
    ("Cinza", "#7f8c8d"),
    ("Branco", "#f5f5f5"),
    ("Preto", "#1a1a1a"),
]


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, library_root: str,
                 db_path: Path, thumbs_dir: Path) -> None:
        super().__init__()
        self._conn = conn  # conexão da thread da UI: SÓ leitura
        self._library_root = Path(library_root)
        self._thumbs_dir = thumbs_dir
        self._db_path = db_path
        self._scan = ScanController(db_path, self._library_root, parent=self)
        self._pipeline = ThumbnailPipeline(thumbs_dir, parent=self)

        self.setWindowTitle("AssetDeck")
        self.resize(1280, 800)

        # --- barra superior: busca + filtros ---
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Buscar por nome…  (ex.: concreto, wood 4k, madeira E rústico, pedra OU metal)"
        )
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

        # Nota mínima e resolução mínima (Fatia 9) — eram QComboBox longos
        # ("Nota: todas") na barra de filtros; viraram botão de ícone
        # compacto na linha do breadcrumb (pedido do Rafael, Fatia 28c).
        self.rating_filter = FilterButton(
            "star-filled", [("Nota: todas", None)] + [(f"★ ≥ {n}", n) for n in range(1, 6)]
        )
        self.rating_filter.changed.connect(self._apply_filters)

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

        # fav_check/group_check/deps_check/hidden_check saíram daqui (Fatia
        # 43) — viram QAction marcável no menu Janela, junto dos toggles de
        # painel (_setup_window_menu). QAction tem isChecked()/setChecked()/
        # toggled igual QCheckBox, então nada que já lê esses 4 atributos
        # precisou mudar, só o tipo do widget.
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.setObjectName("primary")
        self.rescan_btn.setIcon(icons.icon("refresh", theme.current_colors()["on_accent"]))
        self.rescan_btn.clicked.connect(self.start_scan)

        # Busca + reindexar (Fatia 28d/43). "Incluir subpastas" saiu de vez
        # (ele não via caso de uso pra desligar), Tipos/Nota/Resolução foram
        # pra linha do breadcrumb como ícone (Fatia 28c), e os 4 checkboxes
        # de filtro foram pro menu Janela (Fatia 43).
        top = QHBoxLayout()
        top.addWidget(self.search_box, stretch=1)
        top.addWidget(self.progress)
        top.addWidget(self.rescan_btn)

        # --- pastas + grid + detalhes ---
        self.model = AssetGridModel(conn, self._library_root, self._pipeline, parent=self)
        self.grid = AssetGridView()
        self.grid.setModel(self.model)
        self.grid.selectionModel().currentChanged.connect(self._on_selection)
        self.model.dataChanged.connect(self._on_data_changed)
        self.grid.image_dropped.connect(self._on_image_dropped)
        self.grid.asset_preview_dropped.connect(self._on_asset_preview_dropped)
        # Duplo clique = preview ampliado (NÃO abre o arquivo — pedido do Rafael)
        self.preview_popup = PreviewPopup(self)
        self.grid.doubleClicked.connect(self._open_preview)
        # Menu de contexto: agrupar/desagrupar à mão
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._grid_menu)

        self.folders = FolderTree()
        self.folders.dir_selected.connect(self._on_dir_selected)
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
        theme.apply_card_shadow(self.details)
        self.details.notes_saved.connect(self._on_notes_saved)
        self.details.tag_toggled.connect(self._on_tag_toggled)
        self.details.rating_changed.connect(self._on_rating_changed)
        self.details.starred_changed.connect(self._on_starred_changed)
        self.details.preview_add_requested.connect(self._on_preview_add)
        self.details.preview_cover_requested.connect(self._on_preview_cover)
        self.details.preview_remove_requested.connect(self._on_preview_remove)
        self.details.property_value_changed.connect(self._on_property_value_changed)
        self.details.manage_properties_requested.connect(self._manage_properties)
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
        from PySide6.QtWidgets import QSlider

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(asset_grid.MIN_ICON, asset_grid.MAX_ICON)
        self.size_slider.setValue(asset_grid.DEFAULT_ICON)
        self.size_slider.setFixedWidth(110)
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

        # Topo em TRÊS faixas (Fatia 46). Até a Fatia 43 era uma linha só
        # carregando navegação, caminho, 6 categorias e 3 filtros — o Rafael
        # olhou e disse que estava "absurdamente atolado", e o caminho de
        # pasta funda já vinha sendo cortado pelo `_elide_breadcrumb` por
        # falta de espaço. Cada faixa agora responde uma pergunta diferente:
        #
        #   1. onde estou           → setas + caminho
        #   2. o que quero ver      → as 6 categorias
        #   3. como ordenar/refinar → escopo da lista + nota/resolução/cor
        #
        # Os três filtros finos descem para a faixa 3 porque agem sobre a
        # lista que já está na tela, não sobre a pasta — e ali ficam ao lado
        # do rótulo que diz quantos itens sobraram.
        path_row = QHBoxLayout()
        path_row.setSpacing(2)
        path_row.addWidget(self.back_btn)
        path_row.addWidget(self.fwd_btn)
        path_row.addWidget(self.up_btn)
        path_row.addSpacing(6)
        path_row.addWidget(self.breadcrumb, stretch=1)

        category_row = QHBoxLayout()
        category_row.setContentsMargins(0, 0, 0, 0)
        category_row.addWidget(self.categories)
        category_row.addStretch(1)

        list_header_row = QHBoxLayout()
        list_header_row.setSpacing(8)
        list_header_row.addWidget(self.list_scope)
        list_header_row.addWidget(self.list_count)
        list_header_row.addStretch(1)
        list_header_row.addWidget(self.rating_filter)
        list_header_row.addWidget(self.res_filter)
        list_header_row.addWidget(self.color_filter)

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)
        grid_layout.addLayout(path_row)
        grid_layout.addWidget(self._breadcrumb_divider(horizontal=True))
        grid_layout.addLayout(category_row)
        grid_layout.addWidget(self._breadcrumb_divider(horizontal=True))
        grid_layout.addLayout(list_header_row)
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

        # objectName próprio: controles mais baixos SÓ nesta fileira (padding
        # menor), sem afetar botão/campo em nenhum outro lugar do app —
        # pedido do Rafael de enxutar a barra de busca verticalmente.
        top_widget = QWidget()
        top_widget.setObjectName("searchBar")
        top_widget.setLayout(top)
        top_card = theme.make_card(top_widget)

        central = QWidget()
        central.setObjectName("appSurface")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(top_card)
        layout.addWidget(splitter)
        # Bug relatado pelo Rafael: sem isso, desligar os painéis pelo menu
        # Janela deixava a barra de busca inchar até quase tomar a tela
        # inteira — os dois itens do QVBoxLayout disputavam o espaço extra
        # sem prioridade nenhuma entre eles. O splitter (painéis + grade)
        # SEMPRE fica com o espaço sobrando; a barra de busca nunca cresce
        # além do próprio conteúdo.
        layout.setStretchFactor(splitter, 1)
        self.setCentralWidget(central)

        # Navegação de pastas (Fatia 32), mesmas teclas de um navegador.
        # Ctrl+T (tags) virou QAction da Fatia 36 — ver _setup_menu_bar
        # (um QShortcut e uma QAction com a MESMA tecla no mesmo widget
        # geram "ambiguous shortcut" no Qt e nenhum dos dois dispara).
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence("Alt+Left"), self, activated=self._go_back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self._go_forward)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self._go_up)
        self._tag_clipboard: list[int] | None = None

        self._setup_menu_bar()  # Fatia 36 — Arquivo/Editar/Ferramentas/Configurações/Janela
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
        # Slider de tamanho saiu da barra do breadcrumb pro rodapé (Fatia 43,
        # opção C): libera espaço horizontal sem esconder a função.
        self.statusBar().addPermanentWidget(self.size_slider)
        # É uma linha de status, não precisa da altura padrão do Fusion
        # (pedido do Rafael de enxutar o rodapé).
        self.statusBar().setMaximumHeight(24)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self._reload_all()

    # ---- filtros e contagem ----

    def _reload_all(self) -> None:
        """Recarga completa: pastas, tags, checklist de tipos e grid.

        `folders.reload` reseta a seleção para a raiz — antes da Fatia 32
        isso jogava o Rafael de volta pra "tudo" no fim de cada varredura, e
        ainda deixava o breadcrumb mostrando a pasta antiga. Agora a pasta é
        restaurada (ou cai na raiz, se sumiu do disco)."""
        anterior = self.history.current()
        self.folders.reload(self._conn)
        self.tags.reload(self._conn)
        self.collections.reload(self._conn)
        self.smart_collections.reload(self._conn)
        self.categories.reload(self._conn, self._category_counts())
        self.model.reload()
        self._go_to_dir(anterior, record=False)

    def _category_counts(self) -> dict:
        """Contagem por categoria respeitando os filtros ativos (menos o de
        categoria) — é o número que cada botão da barra exibe."""
        return assets_repo.count_by_category(
            self._conn, CATEGORIES, **self._current_filters_dict())

    def _current_filters_dict(self) -> dict:
        """O dicionário de filtros ativos — o mesmo que `list_for_grid`
        aceita. Usado para consultar a grid E para salvar uma Smart
        Collection (Fatia 18)."""
        current = self.folders.currentItem()
        dir_prefix = current.data(0, 32) if current else ""
        return dict(
            search=self.search_box.text().strip(),
            category_filters=self.categories.selection(),
            dir_prefix=dir_prefix,
            # "Incluir subpastas" saiu da UI (pedido do Rafael, Fatia 28c —
            # ele não via caso de uso pra desligar). Sempre True agora.
            include_subdirs=True,
            tag_id=self.tags.current_tag_id(),
            min_rating=self.rating_filter.value(),
            starred_only=self.fav_check.isChecked(),
            min_resolution=self.res_filter.value(),
            include_hidden=self.hidden_check.isChecked(),
            include_dependencies=self.deps_check.isChecked(),
            collection_id=self.collections.current_collection_id(),
            dominant_color=self.color_filter.value(),
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
        """Rotina comum pós-mudança de tags: FTS, sidecars e refresh."""
        assets_repo.rebuild_fts(self._conn)
        for aid in asset_ids:
            sidecar_writer.write_for_asset(self._conn, self._library_root, aid)
        if self.tags.current_tag_id() is not None or self.search_box.text().strip():
            self._apply_filters()  # o filtro ativo pode ter mudado de resultado
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

    def _on_rating_changed(self, rating) -> None:
        alvos = self._selected_asset_ids()
        if not alvos:
            return
        for aid in alvos:
            assets_repo.set_rating(self._conn, aid, rating)
            sidecar_writer.write_for_asset(self._conn, self._library_root, aid)
        self._reload_grid()  # a estrela/nota aparece na grid
        texto = f"{'★' * rating}" if rating else "nota removida"
        sufixo = f" em {len(alvos)} assets" if len(alvos) > 1 else ""
        self.statusBar().showMessage(f"Nota: {texto}{sufixo}")
        if self.rating_filter.value():
            self._apply_filters()

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

    # ---- barra de menus (Fatia 36) ----

    def _setup_brand_bar(self) -> None:
        """Marca à esquerda e contexto à direita, NA MESMA faixa dos menus.

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

        # À direita vai o que NÃO aparece em nenhum outro lugar da tela: qual
        # biblioteca está aberta (são várias desde a Fatia 41) e em que modo.
        # A contagem de assets, que o mockup punha aqui, já está no cabeçalho
        # da lista E no rodapé — um terceiro lugar seria ruído.
        self.brand_context = QLabel()
        self.brand_context.setObjectName("brandContext")
        self.statusBar()  # garante a barra criada antes do primeiro update
        barra.setCornerWidget(self.brand_context, Qt.Corner.TopRightCorner)
        self._update_brand_context()

    def _update_brand_context(self) -> None:
        from assetdeck import config  # import local, como o resto do arquivo

        modo = "Escuro" if config.load_config().get("theme_mode") == "escuro" else "Claro"
        self.brand_context.setText(f"{self._library_root.name}  ·  {modo}   ")

    def _setup_menu_bar(self) -> None:
        """Arquivo, Editar, Ferramentas, Configurações, Janela.

        Reorganiza o que já existia solto (menu ad hoc "Biblioteca" da
        Fatia 19, "Blender" da F2, Ctrl+T como QShortcut avulso) num menu de
        topo de verdade — o app não tinha nenhum até aqui. Nenhuma ação nova
        de lógica: só descoberta (o Rafael não tinha como saber que
        "Relocalizar assets perdidos" existia sem clicar em "Biblioteca" às
        cegas).

        Cada QMenu de topo é guardado em `self._top_menus` (além do atributo
        próprio, tipo `self._menu_arquivo`) — PySide/shiboken nesta versão
        derruba o QMenu de verdade se a única referência Python a ele for
        uma variável local que sai de escopo (`QAction.menu()` reconstrói um
        wrapper nem sempre ligado à mesma contagem de referência do C++);
        guardar a referência aqui é o que evita reconstruir a árvore de menus
        via `menuBar().actions()` — caminho que se mostrou frágil (achado
        escrevendo os testes desta fatia)."""
        self._top_menus: list = []
        self._menu_arquivo = self._setup_file_menu()
        self._menu_editar = self._setup_edit_menu()
        self._menu_ferramentas = ferramentas = self.menuBar().addMenu("Ferramentas")
        self._top_menus.append(ferramentas)
        self.relocate_action = ferramentas.addAction(
            "Relocalizar assets perdidos…", self._relocate_lost_assets
        )
        self.duplicates_action = ferramentas.addAction(
            "Duplicados por conteúdo visual…", self._find_duplicates
        )
        ferramentas.addSeparator()
        ferramentas.addAction("Aplicar template de tags…", self.tags.apply_template_dialog)
        ferramentas.addSeparator()
        self._setup_bridge(ferramentas)  # ponte + submenu "Blender" (F2)
        self._menu_configuracoes = self._setup_settings_menu()
        self._menu_janela = self._setup_window_menu()

    def _setup_file_menu(self):
        from PySide6.QtGui import QKeySequence

        menu = self.menuBar().addMenu("Arquivo")
        self._top_menus.append(menu)
        self.reindex_action = menu.addAction("Reindexar biblioteca", self.start_scan)
        self.reindex_action.setShortcut(QKeySequence("Ctrl+R"))
        menu.addSeparator()
        self.sair_action = menu.addAction("Sair", self.close)
        self.sair_action.setShortcut(QKeySequence.StandardKey.Quit)
        return menu

    def _setup_edit_menu(self):
        from PySide6.QtGui import QKeySequence

        menu = self.menuBar().addMenu("Editar")
        self._top_menus.append(menu)
        tag_action = menu.addAction("Editar tags dos selecionados…", self._quick_tag_dialog)
        tag_action.setShortcut(QKeySequence("Ctrl+T"))
        menu.addSeparator()
        menu.addAction("Copiar tags", self._copy_tags_selected)
        menu.addAction("Colar tags (adicionar)", lambda: self._paste_tags_selected(replace=False))
        menu.addAction("Substituir tags (colar por cima)",
                       lambda: self._paste_tags_selected(replace=True))
        menu.addSeparator()
        menu.addAction("Renomear em lote…", self._batch_rename_dos_selecionados)
        menu.addSeparator()
        menu.addAction("Propriedades customizadas…", self._manage_properties)
        return menu

    def _setup_settings_menu(self):
        from assetdeck import config

        menu = self.menuBar().addMenu("Configurações")
        self._top_menus.append(menu)
        menu.addAction("Preferências…", self._open_preferences)
        menu.addSeparator()

        # Modo escuro (Fatia 43) — aplica na hora, mesmo padrão checkable
        # do menu Janela; não precisa reabrir o app (diferente de
        # bridge_port/bridge_enabled, que já estão de pé quando o app abre).
        self.dark_mode_action = menu.addAction("Modo escuro")
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(config.load_config().get("theme_mode") == "escuro")
        self.dark_mode_action.toggled.connect(self._toggle_dark_mode)

        menu.addSeparator()
        menu.addAction("Abrir pasta de configuração", self._abrir_pasta_config)
        menu.addAction("Abrir pasta de logs", self._abrir_pasta_logs)
        return menu

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
        self.rating_filter.refresh_theme()
        self.res_filter.refresh_theme()
        self.color_filter.refresh_theme()
        self.details.refresh_theme()
        self.sidebar.refresh_theme()
        self._bridge_led.refresh_theme()

        self._search_icon_action.setIcon(icons.icon("search", pal["text_muted"]))
        self.rescan_btn.setIcon(icons.icon("refresh", pal["on_accent"]))
        for botao, nome_icone in (
            (self.back_btn, "arrow-left"),
            (self.fwd_btn, "arrow-right"),
            (self.up_btn, "arrow-up"),
        ):
            botao.setIcon(icons.icon(nome_icone, pal["text_muted"]))

    def _setup_window_menu(self):
        menu = self.menuBar().addMenu("Janela")
        self._top_menus.append(menu)
        # Seções da lateral passam pelo Sidebar (Fatia 45) em vez de esconder o
        # widget direto: assim o rail e o menu ficam sincronizados nos dois
        # sentidos — clicar no ícone desmarca o item do menu e vice-versa.
        # O painel de detalhes não é seção da lateral, então continua sendo um
        # `setVisible` no widget.
        # `_panel_toggles` continua sendo (widget, rótulo): o painel de uma
        # seção da lateral agora é o `SidebarSection`, não um QFrame#card
        # solto. A chave anda junto porque esconder uma seção precisa passar
        # pelo Sidebar (para o rail acompanhar), e o painel de detalhes — que
        # não é seção — segue com `setVisible` direto.
        self._secoes_do_menu = [
            ("pastas", "Pastas"),
            ("tags", "Tags"),
            ("colecoes", "Coleções"),
            ("smart", "Smart Collections"),
        ]
        self._panel_toggles = [
            (self.sidebar.section_widget(chave), rotulo)
            for chave, rotulo in self._secoes_do_menu
        ] + [(self.details, "Painel de detalhes")]

        self._window_menu_actions = []
        self._acoes_por_secao: dict[str, object] = {}
        chaves = [chave for chave, _r in self._secoes_do_menu] + [None]
        for chave, (widget, rotulo) in zip(chaves, self._panel_toggles):
            acao = menu.addAction(rotulo)
            acao.setCheckable(True)
            acao.setChecked(True)
            if chave is None:
                acao.toggled.connect(widget.setVisible)
            else:
                acao.toggled.connect(
                    lambda visivel, k=chave: self.sidebar.set_section_visible(k, visivel)
                )
                self._acoes_por_secao[chave] = acao
            self._window_menu_actions.append(acao)

        # O caminho de volta: rail → menu. Sem isto, desligar uma seção pelo
        # ícone deixaria o item do menu marcado, mentindo sobre o estado.
        self.sidebar.rail.section_toggled.connect(self._on_secao_alternada_pelo_rail)
        menu.addSeparator()

        # Filtros que saíram da barra de busca (Fatia 43) — mesmo padrão
        # marcável dos toggles de painel acima, não entram no "Restaurar
        # layout padrão" (são filtro de conteúdo, não layout de painel).
        self.group_check = menu.addAction("Agrupar PBR")
        self.group_check.setCheckable(True)
        self.group_check.setChecked(True)
        self.group_check.toggled.connect(
            lambda c: (self.model.set_expand_sets(not c), self.refresh_count())
        )

        self.fav_check = menu.addAction("Só favoritos")
        self.fav_check.setCheckable(True)
        self.fav_check.setToolTip("Mostrar só favoritos")
        self.fav_check.toggled.connect(lambda _c: self._apply_filters())

        self.deps_check = menu.addAction("Mostrar dependências")
        self.deps_check.setCheckable(True)
        self.deps_check.setToolTip(
            "Texturas que acompanham um .blend/.fbx irmão (mapas de um material\n"
            "convertido, texturas de um modelo). Desmarcado, você vê só o .blend."
        )
        self.deps_check.toggled.connect(lambda _c: self._apply_filters())

        self.hidden_check = menu.addAction("Mostrar ocultos")
        self.hidden_check.setCheckable(True)
        self.hidden_check.setToolTip(
            "Inclui imagens ocultadas por terem virado preview de um modelo"
        )
        self.hidden_check.toggled.connect(lambda _c: self._apply_filters())

        menu.addSeparator()
        menu.addAction("Restaurar layout padrão", self._restaurar_layout)
        return menu

    def _on_secao_alternada_pelo_rail(self, chave: str, visivel: bool) -> None:
        """Rail → menu Janela. `blockSignals` evita o laço de volta (o menu
        chamaria `set_section_visible`, que remarcaria o rail)."""
        acao = self._acoes_por_secao.get(chave)
        if acao is None:
            log.error("Seção '%s' alternada pelo rail não tem ação no menu.", chave)
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
        self.rating_filter.set_value(query.get("min_rating"))
        self.fav_check.setChecked(bool(query.get("starred_only")))
        self.res_filter.set_value(query.get("min_resolution"))
        self.color_filter.set_value(query.get("dominant_color"))
        self.hidden_check.setChecked(bool(query.get("include_hidden")))
        self.deps_check.setChecked(bool(query.get("include_dependencies")))
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
                "Não achei o Blender nesta máquina. Instale com:\n\n"
                "flatpak install flathub org.blender.Blender",
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
        total = assets_repo.count_active(self._conn)
        shown = self.model.rowCount()
        texto = f"{total} assets" if shown == total else f"{shown} de {total} assets"
        selecionados = len(self._selected_asset_ids())
        if selecionados > 1:
            texto += f" · {selecionados} selecionados"
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

        self.footer_size.setText(human_size(assets_repo.total_bytes(self._conn)))
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
            self.details.load_rating(row["rating"], bool(row["starred"]))
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
            self._hdri_viewer().show_for(caminho)
            return
        maps = None
        if row["asset_type"] == "pbr_set" and self.group_check.isChecked():
            # PBR Material Viewer: botões para alternar entre os mapas do set
            maps = assets_repo.list_files(self._conn, row["id"])
        self.preview_popup.show_for(row, self._library_root,
                                    self._thumb_from_disk(row), maps=maps)

    def _hdri_viewer(self):
        """Criado sob demanda: o contexto OpenGL só é montado se o Rafael
        realmente abrir um HDRI — quem nunca abre não paga nada."""
        if getattr(self, "_hdri_win", None) is None:
            from assetdeck.ui.hdri_viewer import HdriViewer

            self._hdri_win = HdriViewer(self)
        return self._hdri_win

    def _grid_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        selecionados = [
            self.model.row_at(i) for i in self.grid.selectionModel().selectedIndexes()
        ]
        selecionados = [r for r in selecionados if r is not None]
        if not selecionados:
            return
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
        menu.exec(self.grid.mapToGlobal(pos))

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

    def _setup_bridge(self, ferramentas_menu) -> None:
        """`ferramentas_menu`: onde o submenu "Blender" entra (Fatia 36 —
        antes era um menu de topo próprio, `self.menuBar().addMenu("Blender")`)."""
        from assetdeck import config
        from assetdeck.bridge.server import BridgeServer

        # LED + texto (Fatia 49). Só o texto ("Blender: ouvindo :45017") exige
        # ler para saber se está tudo bem; o ponto colorido responde de
        # relance, que é o que se quer de um rodapé.
        self._bridge_led = StatusLed()
        self.statusBar().addPermanentWidget(self._bridge_led)
        self.bridge_status = QLabel()
        self.statusBar().addPermanentWidget(self.bridge_status)

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

        menu = ferramentas_menu.addMenu("Blender")
        menu.addAction("Instalar / atualizar add-on…", self._install_addon)
        menu.addSeparator()
        self.render_action = menu.addAction(
            "Gerar capas dos modelos (render)…", self._start_render
        )
        self.cancel_render_action = menu.addAction(
            "Parar geração de capas", self._stop_render
        )
        self.cancel_render_action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Como usar", self._bridge_help)

        from assetdeck import config as _cfg
        from assetdeck.ui.render_worker import RenderController

        self._render = RenderController(
            self._db_path, self._library_root, _cfg.previews_dir(), parent=self
        )

    # ---- render de capas em lote ----

    def _start_render(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from assetdeck.blender.render import blender_command, models_without_cover
        from assetdeck.db.repos import libraries as libraries_repo

        if self._render.running:
            return
        if blender_command() is None:
            QMessageBox.warning(
                self, "Blender não encontrado",
                "Não achei o Blender nesta máquina. Instale com:\n\n"
                "flatpak install flathub org.blender.Blender",
            )
            return

        lib_id = libraries_repo.get_or_create(self._conn, self._library_root)
        pendentes = models_without_cover(self._conn, lib_id, self._library_root)
        if not pendentes:
            QMessageBox.information(self, "Nada a fazer",
                                    "Todos os modelos .blend já têm capa.")
            return

        resposta = QMessageBox.question(
            self, "Gerar capas dos modelos",
            f"{len(pendentes)} modelo(s) sem capa serão renderizados pelo "
            "Blender, um por vez, em segundo plano.\n\n"
            "Leva alguns segundos por modelo e você pode continuar usando o "
            "AssetDeck normalmente. Começar?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.render_action.setEnabled(False)
        self.cancel_render_action.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(pendentes))
        self._render.start(self._on_render_progress, self._on_render_finished,
                           self._on_render_failed)

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
        for sid in source_ids:
            origem = assets_repo.primary_abs_path(self._conn, sid, self._library_root)
            if origem is None or not can_preview(origem):
                log.info("Origem %d ignorada (sumida ou sem preview visual).", sid)
                continue
            previews_repo.add(self._conn, target_id, origem, config.previews_dir())
            aplicados.append(sid)
        if not aplicados:
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
        if (stats.added or stats.updated or stats.missing or stats.reappeared
                or stats.restored or stats.grouped_sets):
            self._reload_all()  # árvore/tipos/grid só se algo mudou
        else:
            self.refresh_count()
        self.statusBar().showMessage(f"Indexação concluída: {stats.summary()}")
        log.info("UI: indexação concluída — %s", stats.summary())

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.rescan_btn.setEnabled(True)
        self.statusBar().showMessage(f"ERRO na indexação: {message} (detalhes no log)")
        log.error("UI: indexação falhou — %s", message)

    # ---- encerramento limpo ----

    def closeEvent(self, event) -> None:  # noqa: N802 (nome vem do Qt)
        self._scan.shutdown()
        self._pipeline.shutdown()
        if getattr(self, "_bridge", None) is not None:
            self._bridge.stop()
        if getattr(self, "_render", None) is not None:
            self._render.shutdown()
        super().closeEvent(event)
