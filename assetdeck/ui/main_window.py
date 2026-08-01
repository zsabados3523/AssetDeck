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
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer.scanner import ScanStats
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel, AssetGridView
from assetdeck.ui.details_panel import DetailsPanel
from assetdeck.sidecar import writer as sidecar_writer
from assetdeck.ui.folder_tree import FolderTree
from assetdeck.ui.preview_popup import PreviewPopup
from assetdeck.ui.scan_worker import ScanController
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
        self._scan = ScanController(db_path, self._library_root, parent=self)
        self._pipeline = ThumbnailPipeline(thumbs_dir, parent=self)

        self.setWindowTitle("AssetDeck")
        self.resize(1280, 800)

        # --- barra superior: busca + filtros ---
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Buscar por nome…  (ex.: concreto, wood 4k)")
        self.search_box.setClearButtonEnabled(True)
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

        self.rating_combo = QComboBox()
        self.rating_combo.addItem("Nota: todas", None)
        for n in range(1, 6):
            self.rating_combo.addItem("★" * n + f" ≥ {n}", n)
        self.rating_combo.currentIndexChanged.connect(lambda _i: self._apply_filters())

        self.fav_check = QCheckBox("Só ★")
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

        self.count_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(280)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.clicked.connect(self.start_scan)

        top = QHBoxLayout()
        top.addWidget(self.search_box, stretch=1)
        top.addWidget(self.type_filter)
        top.addWidget(self.rating_combo)
        top.addWidget(self.fav_check)
        top.addWidget(self.res_combo)
        top.addWidget(self.subdirs_check)
        top.addWidget(self.group_check)
        top.addWidget(self.deps_check)
        top.addWidget(self.hidden_check)
        top.addWidget(self.count_label)
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
        self.folders.dir_selected.connect(lambda _d: self._apply_filters())

        self.tags = TagTree()
        self.tags.tag_selected.connect(lambda _t: self._apply_filters())
        self.tags.assets_dropped.connect(self._on_assets_dropped)
        self.tags.structure_changed.connect(self._on_tags_structure_changed)

        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self.folders)
        left.addWidget(self.tags)
        left.setSizes([400, 300])
        left.setMinimumWidth(180)
        left.setMaximumWidth(320)

        self.details = DetailsPanel(self._library_root)
        self.details.setMinimumWidth(300)
        self.details.setMaximumWidth(380)
        self.details.notes_saved.connect(self._on_notes_saved)
        self.details.tag_toggled.connect(self._on_tag_toggled)
        self.details.rating_changed.connect(self._on_rating_changed)
        self.details.starred_changed.connect(self._on_starred_changed)
        self.details.preview_add_requested.connect(self._on_preview_add)
        self.details.preview_cover_requested.connect(self._on_preview_cover)
        self.details.preview_remove_requested.connect(self._on_preview_remove)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.grid)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 760, 300])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        # Ctrl+T = diálogo rápido de tags (forma 3 do brief)
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._quick_tag_dialog)
        self._tag_clipboard: list[int] | None = None

        self._setup_bridge()  # ponte com o Blender (F2)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self._reload_all()

    # ---- filtros e contagem ----

    def _reload_all(self) -> None:
        """Recarga completa: pastas, tags, checklist de tipos e grid."""
        self.folders.reload(self._conn)
        self.tags.reload(self._conn)
        self.type_filter.reload(assets_repo.distinct_types(self._conn))
        self.model.reload()
        self._apply_filters()

    def _apply_filters(self) -> None:
        current = self.folders.currentItem()
        dir_prefix = current.data(0, 32) if current else ""
        self.model.set_filters(
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
        )
        self.refresh_count()

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
                self.grid.setCurrentIndex(idx)
        barra.setValue(min(posicao, barra.maximum()))

    def refresh_count(self) -> int:
        total = assets_repo.count_active(self._conn)
        shown = self.model.rowCount()
        if shown == total:
            self.count_label.setText(f"{total} assets")
        else:
            self.count_label.setText(f"{shown} de {total} assets")
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

        menu = self.menuBar().addMenu("Blender")
        menu.addAction("Instalar / atualizar add-on…", self._install_addon)
        menu.addAction("Como usar", self._bridge_help)

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
        self.count_label.setText(f"{live_count} assets")
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
        super().closeEvent(event)
