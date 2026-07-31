"""Grid virtualizada de assets com thumbnails carregadas de forma preguiçosa.

O modelo devolve placeholder na hora e pede a thumb ao pipeline; quando ela
fica pronta, só aquela célula é redesenhada. Rolar nunca trava.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import QListView

from assetdeck.db.repos import assets as assets_repo
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.thumbs.raster import can_thumbnail

log = logging.getLogger(__name__)

CELL = QSize(176, 200)
ICON = 160

# Cor do placeholder por tipo (enquanto não há thumbnail)
TYPE_COLORS = {
    "texture": "#8d99ae", "hdri": "#5f7fbf", "cutout": "#7fae8d",
    "reference": "#b08968", "model": "#c9834a", "scene": "#c9834a",
    "vector": "#9d6bb0", "ies": "#b5a642", "lut": "#5fa8a0",
    "psd": "#4a90d9", "other": "#888888",
}


class AssetGridModel(QAbstractListModel):
    def __init__(self, conn: sqlite3.Connection, library_root: Path,
                 pipeline: ThumbnailPipeline, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._root = library_root
        self._pipeline = pipeline
        self._pipeline.ready.connect(self._on_thumb_ready)
        self._rows: list[sqlite3.Row] = []
        self._row_by_asset: dict[int, int] = {}
        self._placeholders: dict[str, QPixmap] = {}
        QPixmapCache.setCacheLimit(128 * 1024)  # 128MB de thumbs em RAM

    # ---- dados ----

    def reload(self) -> None:
        self.beginResetModel()
        self._rows = assets_repo.list_for_grid(self._conn)
        self._row_by_asset = {r["id"]: i for i, r in enumerate(self._rows)}
        self.endResetModel()
        log.info("Grid recarregada: %d assets.", len(self._rows))
        self._warmup()

    def _warmup(self) -> None:
        """Gera em background as thumbs de toda a biblioteca (visível na frente)."""
        items = [
            (r["id"], self._root / r["rel_path"], r["content_hash"])
            for r in self._rows
            if r["missing_since"] is None and can_thumbnail(self._root / r["rel_path"])
        ]
        self._pipeline.warmup(items)

    def row_at(self, index: QModelIndex) -> sqlite3.Row | None:
        if index.isValid() and 0 <= index.row() < len(self._rows):
            return self._rows[index.row()]
        return None

    # ---- API do Qt ----

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        row = self.row_at(index)
        if row is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return row["name"]
        if role == Qt.ItemDataRole.DecorationRole:
            return self._pixmap_for(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return row["rel_path"]
        return None

    # ---- thumbnails ----

    def _pixmap_for(self, row: sqlite3.Row) -> QPixmap:
        key = f"thumb:{row['content_hash']}"
        cached = QPixmapCache.find(key)
        if cached:
            return cached

        src = self._root / row["rel_path"]
        if row["missing_since"] is None and can_thumbnail(src):
            path = self._pipeline.get_or_request(row["id"], src, row["content_hash"])
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    QPixmapCache.insert(key, pix)
                    return pix
        return self._placeholder(row["asset_type"])

    def _on_thumb_ready(self, asset_id: int, _path: str) -> None:
        i = self._row_by_asset.get(asset_id)
        if i is not None:
            idx = self.index(i)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def _placeholder(self, asset_type: str) -> QPixmap:
        pix = self._placeholders.get(asset_type)
        if pix is None:
            pix = QPixmap(ICON, ICON)
            pix.fill(QColor(TYPE_COLORS.get(asset_type, "#888888")))
            painter = QPainter(pix)
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, asset_type.upper())
            painter.end()
            self._placeholders[asset_type] = pix
        return pix


class AssetGridView(QListView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.Batched)  # nunca congela ao popular
        self.setBatchSize(64)
        self.setUniformItemSizes(True)
        self.setGridSize(CELL)
        self.setIconSize(QSize(ICON, ICON))
        self.setWordWrap(True)
        self.setSpacing(8)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
