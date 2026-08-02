"""Janela principal: grid de thumbnails + painel de detalhes + indexação."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, QTimer
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
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
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel, AssetGridView
from assetdeck.ui.batch_rename_dialog import BatchRenameDialog
from assetdeck.ui.collection_tree import CollectionTree
from assetdeck.ui.details_panel import DetailsPanel
from assetdeck.sidecar import writer as sidecar_writer
from assetdeck.ui.duplicates_dialog import DuplicatesDialog
from assetdeck.ui.folder_tree import FolderTree
from assetdeck.ui.preview_popup import PreviewPopup
from assetdeck.ui.property_defs_dialog import PropertyDefsDialog
from assetdeck.ui.relocate_dialog import RelocateDialog
from assetdeck.ui.scan_worker import ScanController
from assetdeck.ui.smart_collection_panel import SmartCollectionPanel
from assetdeck.ui import icons, theme
from assetdeck.ui.tag_dialogs import QuickTagDialog
from assetdeck.ui.tag_tree import TagTree
from assetdeck.ui.type_filter import TypeFilter

log = logging.getLogger(__name__)


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
        self.search_box.addAction(
            icons.icon("search", theme.TEXT_MUTED),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)  # espera parar de digitar
        self._search_debounce.timeout.connect(self._apply_filters)
        self.search_box.textChanged.connect(
            lambda _t: self._search_debounce.start()
        )

        self.type_filter = TypeFilter()
        self.type_filter.changed.connect(self._apply_filters)

        self.subdirs_check = QCheckBox("Incluir subpastas")
        self.subdirs_check.setChecked(True)
        self.subdirs_check.toggled.connect(lambda _c: self._apply_filters())

        # Toggle do Rafael: ver sets PBR como 1 card (ligado) ou cada mapa
        # separado (desligado). Só visualização — o banco não muda.
        self.group_check = QCheckBox("Agrupar sets PBR")
        self.group_check.setChecked(True)
        self.group_check.toggled.connect(
            lambda c: (self.model.set_expand_sets(not c), self.refresh_count())
        )

        # Filtros da Fatia 9: nota mínima, favoritos, resolução mínima
        from PySide6.QtWidgets import QComboBox

        # Ícone, não texto: nenhuma fonte da máquina tem o glifo ★ (medido com
        # QRawFont na Fatia 24) — o Qt caía numa fonte substituta e saía torto.
        star_icon = icons.icon("star-filled", theme.ACCENT)

        self.rating_combo = QComboBox()
        self.rating_combo.addItem("Nota: todas", None)
        for n in range(1, 6):
            self.rating_combo.addItem(star_icon, f"≥ {n}", n)
        self.rating_combo.currentIndexChanged.connect(lambda _i: self._apply_filters())

        self.fav_check = QCheckBox("Só favoritos")
        self.fav_check.setToolTip("Mostrar só favoritos")
        self.fav_check.toggled.connect(lambda _c: self._apply_filters())

        self.res_combo = QComboBox()
        self.res_combo.addItem("Resolução: todas", None)
        for label, px in (("≥ 1K", 1024), ("≥ 2K", 2048), ("≥ 4K", 4096), ("≥ 8K", 8192)):
            self.res_combo.addItem(label, px)
        self.res_combo.currentIndexChanged.connect(lambda _i: self._apply_filters())

        # Sugestão do Rafael: texturas que acompanham um .blend/.fbx são
        # dependências dele — poluem a grade e o Blender. Ocultas por padrão.
        self.deps_check = QCheckBox("Mostrar dependências")
        self.deps_check.setToolTip(
            "Texturas que acompanham um .blend/.fbx irmão (mapas de um material\n"
            "convertido, texturas de um modelo). Desmarcado, você vê só o .blend."
        )
        self.deps_check.setChecked(False)
        self.deps_check.toggled.connect(lambda _c: self._apply_filters())

        self.hidden_check = QCheckBox("Mostrar ocultos")
        self.hidden_check.setToolTip(
            "Inclui imagens ocultadas por terem virado preview de um modelo"
        )
        self.hidden_check.toggled.connect(lambda _c: self._apply_filters())

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(220)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.setObjectName("primary")
        self.rescan_btn.setIcon(icons.icon("refresh", theme.ON_ACCENT))
        self.rescan_btn.clicked.connect(self.start_scan)

        # Duas fileiras, estilo Connecter (Fatia 28): busca em cima (é a ação
        # mais usada), filtros embaixo — em vez de 11 widgets crus na mesma
        # linha, o que o Rafael descreveu como "amontoado".
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_box, stretch=1)
        search_row.addWidget(self.progress)
        search_row.addWidget(self.rescan_btn)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(10)
        filters_row.addWidget(self.type_filter)
        filters_row.addWidget(self.rating_combo)
        filters_row.addWidget(self.fav_check)
        filters_row.addWidget(self.res_combo)
        filters_row.addWidget(self.subdirs_check)
        filters_row.addWidget(self.group_check)
        filters_row.addWidget(self.deps_check)
        filters_row.addWidget(self.hidden_check)
        filters_row.addStretch(1)

        top = QVBoxLayout()
        top.setSpacing(10)
        top.addLayout(search_row)
        top.addLayout(filters_row)

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

        # Cada painel é um QFrame#card translúcido em volta de uma view
        # transparente — o viewport de uma QTreeWidget/QListView pinta
        # retângulo no canto e vaza por cima de qualquer border-radius posto
        # nela diretamente, então o card por fora é obrigatório (Fatia 24).
        left = QSplitter(Qt.Orientation.Vertical)
        left.setHandleWidth(10)
        left.addWidget(theme.make_card(self.folders, titulo="Pastas"))
        left.addWidget(theme.make_card(self.tags, titulo="Tags"))
        left.addWidget(theme.make_card(self.collections, titulo="Coleções"))
        left.addWidget(theme.make_card(self.smart_collections, titulo="Smart Collections"))
        left.setSizes([280, 200, 200, 200])
        left.setMinimumWidth(200)
        left.setMaximumWidth(340)

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

        # Caminho navegável acima da grade (Fatia 28, estilo Connecter): a
        # única pista de "onde estou" antes disso era o item selecionado na
        # árvore de pastas — fácil de perder de vista depois de rolar.
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("sectionTitle")
        self._update_breadcrumb("")

        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)
        grid_layout.addWidget(self.breadcrumb)
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
        splitter.setSizes([240, 740, 300])

        top_widget = QWidget()
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
        self.setCentralWidget(central)

        # Ctrl+T = diálogo rápido de tags (forma 3 do brief)
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._quick_tag_dialog)
        self._tag_clipboard: list[int] | None = None

        self._setup_bridge()  # ponte com o Blender (F2)
        self._setup_library_menu()  # relocalizar assets perdidos (Fatia 19)

        # Contagem sempre visível no rodapé (Fatia 28) — antes vivia num
        # QLabel solto na barra de filtros, junto de mais 10 widgets.
        self.footer_count = QLabel()
        self.statusBar().addPermanentWidget(self.footer_count)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self._reload_all()

    # ---- filtros e contagem ----

    def _reload_all(self) -> None:
        """Recarga completa: pastas, tags, checklist de tipos e grid."""
        self.folders.reload(self._conn)
        self.tags.reload(self._conn)
        self.collections.reload(self._conn)
        self.smart_collections.reload(self._conn)
        self.type_filter.reload(assets_repo.distinct_types(self._conn))
        self.model.reload()
        self._apply_filters()

    def _current_filters_dict(self) -> dict:
        """O dicionário de filtros ativos — o mesmo que `list_for_grid`
        aceita. Usado para consultar a grid E para salvar uma Smart
        Collection (Fatia 18)."""
        current = self.folders.currentItem()
        dir_prefix = current.data(0, 32) if current else ""
        return dict(
            search=self.search_box.text().strip(),
            asset_types=self.type_filter.selected(),
            dir_prefix=dir_prefix,
            include_subdirs=self.subdirs_check.isChecked(),
            tag_id=self.tags.current_tag_id(),
            min_rating=self.rating_combo.currentData(),
            starred_only=self.fav_check.isChecked(),
            min_resolution=self.res_combo.currentData(),
            include_hidden=self.hidden_check.isChecked(),
            include_dependencies=self.deps_check.isChecked(),
            collection_id=self.collections.current_collection_id(),
        )

    def _apply_filters(self) -> None:
        self.model.set_filters(**self._current_filters_dict())
        self.refresh_count()

    def _update_breadcrumb(self, dir_prefix: str) -> None:
        """"" -> biblioteca inteira; "A/B" -> "Biblioteca › A › B"."""
        if not dir_prefix:
            self.breadcrumb.setText("BIBLIOTECA (TUDO)")
        else:
            trilha = " › ".join(dir_prefix.split("/"))
            self.breadcrumb.setText(f"BIBLIOTECA › {trilha}".upper())

    def _on_dir_selected(self, dir_prefix: str) -> None:
        self._update_breadcrumb(dir_prefix)
        self._apply_filters()

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
        if self.rating_combo.currentData():
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

    # ---- relocalizar assets perdidos (Fatia 19) ----

    def _setup_library_menu(self) -> None:
        menu = self.menuBar().addMenu("Biblioteca")
        self.relocate_action = menu.addAction(
            "Relocalizar assets perdidos…", self._relocate_lost_assets
        )
        self.duplicates_action = menu.addAction(
            "Duplicados por conteúdo visual…", self._find_duplicates
        )

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
        reindexação) mantém a visão sempre recalculada."""
        self.search_box.setText(query.get("search") or "")
        self.type_filter.set_selected(query.get("asset_types") or [])
        self.subdirs_check.setChecked(bool(query.get("include_subdirs", True)))
        self._set_combo_value(self.rating_combo, query.get("min_rating"))
        self.fav_check.setChecked(bool(query.get("starred_only")))
        self._set_combo_value(self.res_combo, query.get("min_resolution"))
        self.hidden_check.setChecked(bool(query.get("include_hidden")))
        self.deps_check.setChecked(bool(query.get("include_dependencies")))
        dir_prefix = query.get("dir_prefix") or ""
        self.folders.select(dir_prefix)
        self._update_breadcrumb(dir_prefix)
        self.tags.select(query.get("tag_id"))
        self.collections.select(query.get("collection_id"))
        self._apply_filters()

    @staticmethod
    def _set_combo_value(combo, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

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
        return total

    # ---- seleção / detalhes ----

    def _thumb_from_disk(self, row) -> "QPixmap | None":
        """Thumb em 256px direto do cache em disco (a da RAM está reduzida
        para caber na célula da grid — ampliá-la ficaria borrado)."""
        from PySide6.QtGui import QPixmap

        from assetdeck.thumbs.cache import thumb_path

        p = thumb_path(self._thumbs_dir, row["content_hash"])
        if p.exists():
            pix = QPixmap(str(p))
            if not pix.isNull():
                return pix
        return QPixmapCache.find(f"thumb:{row['content_hash']}")

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
        maps = None
        if row["asset_type"] == "pbr_set" and self.group_check.isChecked():
            # PBR Material Viewer: botões para alternar entre os mapas do set
            maps = assets_repo.list_files(self._conn, row["id"])
        self.preview_popup.show_for(row, self._library_root,
                                    self._thumb_from_disk(row), maps=maps)

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

    def _setup_bridge(self) -> None:
        from assetdeck import config
        from assetdeck.bridge.server import BridgeServer

        self.bridge_status = QLabel()
        self.statusBar().addPermanentWidget(self.bridge_status)

        cfg = config.load_config()
        self._bridge = None
        if not cfg.get("bridge_enabled", True):
            self.bridge_status.setText("Blender: ponte desligada")
            return

        token = config.ensure_bridge_token(cfg)
        porta = int(cfg.get("bridge_port", 45017))
        self._bridge = BridgeServer(self._conn, self._library_root, token,
                                    thumbs_dir=self._thumbs_dir, parent=self)
        if self._bridge.start(porta):
            self.bridge_status.setText(f"Blender: ouvindo :{self._bridge.port}")
        else:
            self.bridge_status.setText("Blender: porta ocupada (ver log)")
        self._bridge.client_connected.connect(
            lambda: self.bridge_status.setText("Blender: conectado ✓")
        )
        self._bridge.client_disconnected.connect(
            lambda: self.bridge_status.setText(f"Blender: ouvindo :{self._bridge.port}")
        )
        # O Blender salvou algo novo na biblioteca → reindexar
        self._bridge.rescan_requested.connect(self.start_scan)

        menu = self.menuBar().addMenu("Blender")
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
        """Asset de imagem arrastado de dentro da grid sobre um model (Fatia 10b)."""
        from assetdeck import config
        from assetdeck.thumbs.preview import can_preview

        alvo = self._conn.execute(
            "SELECT name, asset_type FROM assets WHERE id = ?", (target_id,)
        ).fetchone()
        if alvo is None or alvo["asset_type"] not in ("model", "scene"):
            self.statusBar().showMessage(
                "Previews internos só podem ser aplicados a MODELOS (.blend/.fbx/.obj…)"
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
