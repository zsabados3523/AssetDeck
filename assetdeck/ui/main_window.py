"""Janela principal. Na Fatia 1 ela só prova que o esqueleto está vivo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from assetdeck import __version__


class MainWindow(QMainWindow):
    def __init__(self, asset_count: int, library_root: str, db_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("AssetDeck")
        self.resize(900, 600)

        title = QLabel("AssetDeck")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(28)
        font.setBold(True)
        title.setFont(font)

        count_label = QLabel(f"{asset_count} assets na biblioteca")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cfont = count_label.font()
        cfont.setPointSize(14)
        count_label.setFont(cfont)

        lib_label = QLabel(f"Biblioteca: {library_root}")
        lib_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lib_label.setStyleSheet("color: gray;")

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(count_label)
        layout.addSpacing(12)
        layout.addWidget(lib_label)
        layout.addStretch()

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.statusBar().showMessage(f"v{__version__} · banco: {db_path}")
