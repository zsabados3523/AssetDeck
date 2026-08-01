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
    notes_saved = Signal(int, str)        # asset_id, texto da nota
    tag_toggled = Signal(int, int, bool)  # asset_id, tag_id, marcado?
    rating_changed = Signal(object)       # int 1–5 ou None (limpar)
    starred_changed = Signal(bool)

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

        # Rating (5 estrelas clicáveis) + favorito — Fatia 9
        from PySide6.QtWidgets import QHBoxLayout as _QHBox

        self._rating: int | None = None
        stars_row = _QHBox()
        self.star_btns: list[QPushButton] = []
        for i in range(1, 6):
            b = QPushButton("☆")
            b.setFlat(True)
            b.setMaximumWidth(28)
            b.clicked.connect(lambda _c=False, n=i: self._on_star_clicked(n))
            self.star_btns.append(b)
            stars_row.addWidget(b)
        self.fav_btn = QPushButton("☆ Favorito")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self._on_fav_toggled)
        stars_row.addWidget(self.fav_btn)
        stars_row.addStretch()

        # Aviso de edição em massa (sugestão do Rafael): com N selecionados,
        # tag/nota de estrela/favorito valem para todos
        self.multi_label = QLabel()
        self.multi_label.setStyleSheet("color: #b07d2b; font-weight: bold;")
        self.multi_label.setVisible(False)

        # Tags com checkbox (forma 2 de taggear): marcar/desmarcar aplica na hora
        from PySide6.QtWidgets import QTreeWidget

        tags_label = QLabel("Tags:")
        self.tags_tree = QTreeWidget()
        self.tags_tree.setHeaderHidden(True)
        self.tags_tree.setMaximumHeight(150)
        self.tags_tree.itemChanged.connect(self._on_tag_item_changed)
        self._loading_tags = False

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
        layout.addLayout(stars_row)
        layout.addWidget(self.multi_label)
        layout.addWidget(tags_label)
        layout.addWidget(self.tags_tree)
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

    # ---- rating / favorito ----

    def set_multi_count(self, n: int) -> None:
        """n>1: avisa que as edições valem para todos os selecionados."""
        self.multi_label.setText(f"⚠ Editando {n} assets selecionados de uma vez")
        self.multi_label.setVisible(n > 1)

    def _paint_stars(self) -> None:
        for i, b in enumerate(self.star_btns, start=1):
            b.setText("★" if self._rating and i <= self._rating else "☆")

    def load_rating(self, rating: int | None, starred: bool) -> None:
        self._rating = rating
        self._paint_stars()
        self.fav_btn.blockSignals(True)
        self.fav_btn.setChecked(starred)
        self.fav_btn.setText("★ Favorito" if starred else "☆ Favorito")
        self.fav_btn.blockSignals(False)

    def _on_star_clicked(self, n: int) -> None:
        # Clicar na estrela da nota atual limpa a nota
        self._rating = None if self._rating == n else n
        self._paint_stars()
        self.rating_changed.emit(self._rating)

    def _on_fav_toggled(self, checked: bool) -> None:
        self.fav_btn.setText("★ Favorito" if checked else "☆ Favorito")
        self.starred_changed.emit(checked)

    # ---- tags (checkbox interativo) ----

    def load_tags(self, tag_rows: list, checked_ids: set[int]) -> None:
        """Recebe a árvore de tags e quais estão marcadas para o asset atual."""
        from PySide6.QtWidgets import QTreeWidgetItem

        self._loading_tags = True
        self.tags_tree.clear()
        itens: dict[int, "QTreeWidgetItem"] = {}
        for r in tag_rows:
            item = QTreeWidgetItem([r["name"]])
            item.setData(0, 32, r["id"])
            item.setCheckState(
                0, Qt.CheckState.Checked if r["id"] in checked_ids
                else Qt.CheckState.Unchecked
            )
            pai = itens.get(r["parent_id"])
            if pai is not None:
                pai.addChild(item)
            else:
                self.tags_tree.addTopLevelItem(item)
            itens[r["id"]] = item
        self.tags_tree.expandAll()
        self._loading_tags = False

    def _on_tag_item_changed(self, item, _col) -> None:
        if self._loading_tags or self._current_asset_id is None:
            return
        self.tag_toggled.emit(
            self._current_asset_id, item.data(0, 32),
            item.checkState(0) == Qt.CheckState.Checked,
        )

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
