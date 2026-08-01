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
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.indexer.grouper import PRIMARY_ORDER
from assetdeck.thumbs.preview import can_preview, load_full_image

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
            img = load_full_image(self._path)  # HDR/EXR já vem tonemapado
            w, h = img.width, img.height
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

        # Barra do "PBR Material Viewer": um botão por mapa do set
        self.maps_bar = QWidget()
        self._maps_layout = QHBoxLayout(self.maps_bar)
        self._maps_layout.setContentsMargins(0, 0, 0, 0)
        self._maps_group = QButtonGroup(self)
        self._maps_group.setExclusive(True)
        self.maps_bar.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.image_label, stretch=1)
        layout.addWidget(self.maps_bar)
        layout.addWidget(self.info_label)

        self._sig = _Signaller()
        self._sig.loaded.connect(self._on_loaded)
        self._sig.failed.connect(self._on_failed)
        self._loading_for: Path | None = None
        self._library_root: Path | None = None

    def show_for(self, row: sqlite3.Row, library_root: Path,
                 thumb: QPixmap | None, maps: list | None = None) -> None:
        self._library_root = library_root
        self.setWindowTitle(row["name"])

        if thumb and not thumb.isNull():
            self.image_label.setPixmap(self._fit(thumb))
        else:
            self.image_label.setText("(sem preview)")

        self._build_maps_bar(maps)
        alvo = library_root / row["rel_path"]
        cover = dict(row).get("cover_path")  # funciona para dict e sqlite3.Row
        if cover and not can_preview(alvo):
            # Asset sem preview visual (.blend, .pdf…) mas com capa escolhida
            # pelo usuário: o popup mostra a capa em resolução completa
            alvo = Path(cover)
        self._load(alvo)
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- PBR Material Viewer (sets agrupados) ----

    def _build_maps_bar(self, maps: list | None) -> None:
        for btn in self._maps_group.buttons():
            self._maps_group.removeButton(btn)
            btn.deleteLater()
        if not maps or len(maps) < 2:
            self.maps_bar.setVisible(False)
            return
        ordenados = sorted(
            maps, key=lambda m: PRIMARY_ORDER.index(m["map_role"])
            if m["map_role"] in PRIMARY_ORDER else 99,
        )
        for m in ordenados:
            btn = QPushButton(m["map_role"] if m["map_role"] != "none" else "arquivo")
            btn.setCheckable(True)
            rel = m["rel_path"]
            btn.clicked.connect(lambda _c=False, r=rel: self._on_map_clicked(r))
            self._maps_group.addButton(btn)
            self._maps_layout.addWidget(btn)
        self._maps_group.buttons()[0].setChecked(True)
        self.maps_bar.setVisible(True)

    def _on_map_clicked(self, rel_path: str) -> None:
        if self._library_root is not None:
            self._load(self._library_root / rel_path)

    def _load(self, path: Path) -> None:
        self._loading_for = path
        if can_preview(path) and path.exists():
            self.info_label.setText("Carregando resolução completa…")
            QThreadPool.globalInstance().start(_LoadJob(self._sig, path))
        else:
            self.info_label.setText(
                "Preview em resolução completa disponível só para imagens "
                "e HDR/EXR por enquanto — Esc fecha"
            )

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
