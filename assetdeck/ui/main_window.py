"""Janela principal: grid de thumbnails + painel de detalhes + indexação."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
from assetdeck.ui.scan_worker import ScanController

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

        # --- barra superior ---
        self.count_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(320)
        self.rescan_btn = QPushButton("Reindexar")
        self.rescan_btn.clicked.connect(self.start_scan)

        top = QHBoxLayout()
        top.addWidget(self.count_label)
        top.addStretch()
        top.addWidget(self.progress)
        top.addWidget(self.rescan_btn)

        # --- grid + detalhes ---
        self.model = AssetGridModel(conn, self._library_root, self._pipeline, parent=self)
        self.grid = AssetGridView()
        self.grid.setModel(self.model)
        self.grid.selectionModel().currentChanged.connect(self._on_selection)
        self.model.dataChanged.connect(self._on_data_changed)

        self.details = DetailsPanel(self._library_root)
        self.details.setMinimumWidth(300)
        self.details.setMaximumWidth(380)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.grid)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self.model.reload()
        self.refresh_count()

    # ---- contagem ----

    def refresh_count(self) -> int:
        count = assets_repo.count_active(self._conn)
        self.count_label.setText(f"{count} assets")
        return count

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
        self.refresh_count()
        if stats.added or stats.updated or stats.missing or stats.reappeared:
            self.model.reload()  # só recarrega a grid se algo mudou
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
