"""Janela principal: contagem ao vivo + progresso da indexação em background."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck import __version__
from assetdeck.db.repos import assets as assets_repo
from assetdeck.indexer.scanner import ScanStats
from assetdeck.ui.scan_worker import ScanController

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, library_root: str, db_path: Path) -> None:
        super().__init__()
        self._conn = conn  # conexão da thread da UI: SÓ leitura
        self._library_root = library_root
        self._scan = ScanController(db_path, Path(library_root), parent=self)

        self.setWindowTitle("AssetDeck")
        self.resize(900, 600)

        title = QLabel("AssetDeck")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(28)
        font.setBold(True)
        title.setFont(font)

        self.count_label = QLabel()
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cfont = self.count_label.font()
        cfont.setPointSize(14)
        self.count_label.setFont(cfont)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(420)

        self.rescan_btn = QPushButton("Reindexar biblioteca")
        self.rescan_btn.setMaximumWidth(220)
        self.rescan_btn.clicked.connect(self.start_scan)

        lib_label = QLabel(f"Biblioteca: {library_root}")
        lib_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lib_label.setStyleSheet("color: gray;")

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.count_label)
        layout.addSpacing(8)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.rescan_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(12)
        layout.addWidget(lib_label)
        layout.addStretch()

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
        self.refresh_count()

    # ---- contagem ----

    def refresh_count(self) -> int:
        count = assets_repo.count_active(self._conn)
        self.count_label.setText(f"{count} assets na biblioteca")
        return count

    # ---- varredura ----

    def start_scan(self) -> None:
        if self._scan.running:
            return
        self.rescan_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # "ocupado" até o total ser conhecido
        self.statusBar().showMessage("Indexando biblioteca…")
        self._scan.start(self._on_progress, self._on_finished, self._on_failed)

    def _on_progress(self, done: int, total: int, live_count: int) -> None:
        if self.progress.maximum() != total:
            self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.count_label.setText(f"{live_count} assets na biblioteca")
        self.statusBar().showMessage(f"Indexando… {done}/{total} arquivos")

    def _on_finished(self, stats: ScanStats) -> None:
        self.progress.setVisible(False)
        self.rescan_btn.setEnabled(True)
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
        super().closeEvent(event)
