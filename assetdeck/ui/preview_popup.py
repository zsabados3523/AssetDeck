"""Popup de preview ampliado (duplo clique no asset — pedido do Rafael).

Mostra a imagem em resolução completa, ajustada à tela. A decodificação do
arquivo original (que pode ter 100MB) acontece em thread — o popup abre na
hora com a thumbnail e troca pela versão cheia quando pronta. Esc fecha.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from assetdeck.thumbs.raster import can_thumbnail, open_image

log = logging.getLogger(__name__)


class _Signaller(QObject):
    loaded = Signal(QImage, int, int)  # imagem, largura original, altura original
    failed = Signal(str)


class _LoadJob(QRunnable):
    def __init__(self, sig: _Signaller, path: Path) -> None:
        super().__init__()
        self._sig = sig
        self._path = path

    def run(self) -> None:
        try:
            with open_image(self._path) as img:
                w, h = img.width, img.height
                if img.mode in ("I;16", "I;16L", "I;16B", "I;16N", "I", "F"):
                    img = img.point(lambda v: v / 256).convert("L") \
                        if img.mode.startswith("I") else img.convert("L")
                img = img.convert("RGBA")
                qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height,
                              QImage.Format.Format_RGBA8888).copy()
            self._sig.loaded.emit(qimg, w, h)
        except Exception as exc:
            log.exception("Preview ampliado falhou para %s", self._path)
            self._sig.failed.emit(str(exc))


class PreviewPopup(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("color: gray;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.image_label, stretch=1)
        layout.addWidget(self.info_label)

        self._sig = _Signaller()
        self._sig.loaded.connect(self._on_loaded)
        self._sig.failed.connect(self._on_failed)
        self._loading_for: Path | None = None

    def show_for(self, row: sqlite3.Row, library_root: Path,
                 thumb: QPixmap | None) -> None:
        path = library_root / row["rel_path"]
        self.setWindowTitle(row["name"])
        self._loading_for = path

        if thumb and not thumb.isNull():
            self.image_label.setPixmap(self._fit(thumb))
        else:
            self.image_label.setText("(sem preview)")

        if can_thumbnail(path) and path.exists():
            self.info_label.setText("Carregando resolução completa…")
            QThreadPool.globalInstance().start(_LoadJob(self._sig, path))
        else:
            self.info_label.setText(
                "Preview em resolução completa disponível só para imagens "
                "comuns por enquanto (HDRI/EXR chegam na Fatia 7) — Esc fecha"
            )
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- resultado do carregamento ----

    def _on_loaded(self, qimg: QImage, w: int, h: int) -> None:
        pix = QPixmap.fromImage(qimg)
        self.image_label.setPixmap(self._fit(pix))
        self.info_label.setText(f"{w} × {h} px — Esc fecha")

    def _on_failed(self, message: str) -> None:
        self.info_label.setText(f"Não consegui carregar a imagem completa: {message}")

    def _fit(self, pix: QPixmap) -> QPixmap:
        """Ajusta à área útil da tela (90%), sem nunca ampliar além do original."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.9), int(screen.height() * 0.85)
        fitted = pix.scaled(min(pix.width(), max_w), min(pix.height(), max_h),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        self.resize(fitted.width() + 40, fitted.height() + 80)
        return fitted
