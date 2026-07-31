"""Painel de detalhes do asset selecionado + abrir pasta/arquivo."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.thumbs.raster import can_thumbnail

log = logging.getLogger(__name__)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


class DetailsPanel(QWidget):
    notes_saved = Signal(int, str)  # asset_id, texto da nota

    def __init__(self, library_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._root = library_root
        self._current: Path | None = None
        self._current_asset_id: int | None = None
        self._loaded_notes: str = ""

        self.preview = QLabel("Selecione um asset")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(220, 220)

        self.name = QLabel("—")
        self.name.setWordWrap(True)
        nfont = self.name.font()
        nfont.setPointSize(12)
        nfont.setBold(True)
        self.name.setFont(nfont)

        self.f_type = QLabel("—")
        self.f_dims = QLabel("—")
        self.f_size = QLabel("—")
        self.f_format = QLabel("—")
        self.f_path = QLabel("—")
        self.f_path.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Tipo:", self.f_type)
        form.addRow("Resolução:", self.f_dims)
        form.addRow("Tamanho:", self.f_size)
        form.addRow("Formato:", self.f_format)
        form.addRow("Caminho:", self.f_path)

        self.open_folder_btn = QPushButton("Abrir pasta")
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.open_file_btn = QPushButton("Abrir com app padrão")
        self.open_file_btn.clicked.connect(self._open_file)
        self._set_buttons(False)

        notes_label = QLabel("Notas:")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Anotações suas sobre este asset…")
        self.notes_edit.setMaximumHeight(110)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.save_notes_btn = QPushButton("Salvar nota")
        self.save_notes_btn.setEnabled(False)
        self.save_notes_btn.clicked.connect(self._save_notes)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addWidget(self.name)
        layout.addLayout(form)
        layout.addWidget(self.open_folder_btn)
        layout.addWidget(self.open_file_btn)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_edit)
        layout.addWidget(self.save_notes_btn)
        layout.addStretch()

    def _set_buttons(self, enabled: bool) -> None:
        self.open_folder_btn.setEnabled(enabled)
        self.open_file_btn.setEnabled(enabled)

    # ---- exibição ----

    def show_asset(self, row: sqlite3.Row, thumb: QPixmap | None) -> None:
        path = self._root / row["rel_path"]
        self._current = path
        self._current_asset_id = row["id"]
        self._loaded_notes = row["notes"] or ""
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(self._loaded_notes)
        self.notes_edit.blockSignals(False)
        self.save_notes_btn.setEnabled(False)

        if thumb and not thumb.isNull():
            self.preview.setPixmap(
                thumb.scaled(260, 260, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("(sem preview ainda)")

        self.name.setText(row["name"])
        self.f_type.setText(row["asset_type"])
        self.f_dims.setText(self._read_dims(path))
        self.f_size.setText(human_size(row["size_bytes"]))
        self.f_format.setText(path.suffix.lstrip(".").upper() or "—")
        self.f_path.setText(row["rel_path"])
        sumido = row["missing_since"] is not None
        if sumido:
            self.f_path.setText(f"{row['rel_path']}  ⚠ ARQUIVO SUMIDO")
        self._set_buttons(not sumido)

    def _read_dims(self, path: Path) -> str:
        """Resolução lida na hora (só formatos raster; os demais mostram —)."""
        if not can_thumbnail(path) or not path.exists():
            return "—"
        try:
            from assetdeck.thumbs.raster import open_image

            with open_image(path) as img:
                return f"{img.width} × {img.height}"
        except Exception:
            log.exception("Não consegui ler dimensões de %s", path)
            return "—"

    # ---- notas ----

    def _on_notes_changed(self) -> None:
        mudou = self.notes_edit.toPlainText() != self._loaded_notes
        self.save_notes_btn.setEnabled(mudou and self._current_asset_id is not None)

    def _save_notes(self) -> None:
        if self._current_asset_id is None:
            return
        texto = self.notes_edit.toPlainText()
        self._loaded_notes = texto
        self.save_notes_btn.setEnabled(False)
        self.notes_saved.emit(self._current_asset_id, texto)

    # ---- ações ----

    def _open_folder(self) -> None:
        if self._current:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current.parent)))

    def _open_file(self) -> None:
        if self._current:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current)))
