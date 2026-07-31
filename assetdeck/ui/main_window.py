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
from assetdeck.indexer.scanner import ScanStats
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel, AssetGridView
from assetdeck.ui.details_panel import DetailsPanel
from assetdeck.sidecar import writer as sidecar_writer
from assetdeck.ui.folder_tree import FolderTree
from assetdeck.ui.scan_worker import ScanController
from assetdeck.ui.type_filter import TypeFilter

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, library_root: str,
                 db_path: Path, thumbs_dir: Path) -> None:
        super().__init__()
        self._conn = conn  # conexão da thread da UI: SÓ leitura
        self._library_root = Path(library_root)
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

        self.count_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(280)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.clicked.connect(self.start_scan)

        top = QHBoxLayout()
        top.addWidget(self.search_box, stretch=1)
        top.addWidget(self.type_filter)
        top.addWidget(self.subdirs_check)
        top.addWidget(self.count_label)
        top.addWidget(self.progress)
        top.addWidget(self.rescan_btn)

        # --- pastas + grid + detalhes ---
        self.model = AssetGridModel(conn, self._library_root, self._pipeline, parent=self)
        self.grid = AssetGridView()
        self.grid.setModel(self.model)
        self.grid.selectionModel().currentChanged.connect(self._on_selection)
        self.model.dataChanged.connect(self._on_data_changed)

        self.folders = FolderTree()
        self.folders.setMinimumWidth(180)
        self.folders.setMaximumWidth(320)
        self.folders.dir_selected.connect(lambda _d: self._apply_filters())

        self.details = DetailsPanel(self._library_root)
        self.details.setMinimumWidth(300)
        self.details.setMaximumWidth(380)
        self.details.notes_saved.connect(self._on_notes_saved)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.folders)
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

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self._reload_all()

    # ---- filtros e contagem ----

    def _reload_all(self) -> None:
        """Recarga completa: árvore de pastas, checklist de tipos e grid."""
        self.folders.reload(self._conn)
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
        )
        self.refresh_count()

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

    def refresh_count(self) -> int:
        total = assets_repo.count_active(self._conn)
        shown = self.model.rowCount()
        if shown == total:
            self.count_label.setText(f"{total} assets")
        else:
            self.count_label.setText(f"{shown} de {total} assets")
        return total

    # ---- seleção / detalhes ----

    def _on_selection(self, current: QModelIndex, _previous: QModelIndex) -> None:
        row = self.model.row_at(current)
        if row is not None:
            thumb = QPixmapCache.find(f"thumb:{row['content_hash']}")
            self.details.show_asset(row, thumb)

    def _on_data_changed(self, top_left: QModelIndex, _br, _roles) -> None:
        # Se a thumb que acabou de ficar pronta é a do asset selecionado,
        # atualiza o preview grande do painel.
        if top_left == self.grid.currentIndex():
            self._on_selection(top_left, QModelIndex())

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
        if stats.added or stats.updated or stats.missing or stats.reappeared:
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
        super().closeEvent(event)
