"""Grid virtualizada de assets com thumbnails carregadas de forma preguiçosa.

O modelo devolve placeholder na hora e pede a thumb ao pipeline; quando ela
fica pronta, só aquela célula é redesenhada. Rolar nunca trava.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import QListView

MIME_ASSETS = "application/x-assetdeck-asset-ids"

from assetdeck.db.repos import assets as assets_repo
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.thumbs.preview import can_preview

log = logging.getLogger(__name__)

CELL = QSize(176, 200)
ICON = 160

# Cor do placeholder por tipo (enquanto não há thumbnail)
TYPE_COLORS = {
    "texture": "#8d99ae", "pbr_set": "#5a8a5a", "hdri": "#5f7fbf", "cutout": "#7fae8d",
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
        # Filtros ativos (Fatia 4; tipos viraram lista na Fatia 5)
        self._search: str | None = None
        self._asset_types: list[str] = []
        self._dir_prefix: str | None = None
        self._include_subdirs: bool = True
        self._expand_sets: bool = False  # toggle 'agrupar' desligado (Fatia 7)
        self._tag_id: int | None = None  # filtro por tag (Fatia 8)
        QPixmapCache.setCacheLimit(128 * 1024)  # 128MB de thumbs em RAM

    # ---- dados ----

    def set_filters(self, search: str | None = None, asset_types: list[str] | None = None,
                    dir_prefix: str | None = None, include_subdirs: bool = True,
                    tag_id: int | None = None) -> None:
        self._search = search or None
        self._asset_types = asset_types or []
        self._dir_prefix = dir_prefix or None
        self._include_subdirs = include_subdirs
        self._tag_id = tag_id
        self._requery()

    def set_expand_sets(self, expand: bool) -> None:
        """Toggle do Rafael: False = sets agrupados (1 card); True = cada mapa
        aparece como card próprio. Só muda a VISUALIZAÇÃO, nunca o banco."""
        if expand != self._expand_sets:
            self._expand_sets = expand
            self._requery()

    def reload(self) -> None:
        """Recarga completa (pós-varredura): refaz a consulta e o pré-aquecimento."""
        self._requery()
        self._warmup()

    def _requery(self) -> None:
        self.beginResetModel()
        self._rows = assets_repo.list_for_grid(
            self._conn, search=self._search, asset_types=self._asset_types,
            dir_prefix=self._dir_prefix, include_subdirs=self._include_subdirs,
            expand_sets=self._expand_sets, tag_id=self._tag_id,
        )
        self._row_by_asset = {r["id"]: i for i, r in enumerate(self._rows)}
        self.endResetModel()
        log.info("Grid: %d assets (filtros: busca=%r tipos=%r pasta=%r subpastas=%s)",
                 len(self._rows), self._search, self._asset_types,
                 self._dir_prefix, self._include_subdirs)

    def _warmup(self) -> None:
        """Gera em background as thumbs da biblioteca TODA — inclusive os
        mapas não-capa dos sets (o modo expandido precisa deles prontos)."""
        items = [
            (r["id"], self._root / r["rel_path"], r["content_hash"])
            for r in assets_repo.list_for_grid(self._conn, expand_sets=True)
            if r["missing_since"] is None and can_preview(self._root / r["rel_path"])
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

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return [MIME_ASSETS]

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        """Arrastar assets → soltar numa tag (forma 1 de taggear)."""
        ids = sorted({r["id"] for r in (self.row_at(i) for i in indexes) if r})
        mime = QMimeData()
        mime.setData(MIME_ASSETS, ",".join(str(i) for i in ids).encode())
        return mime

    # ---- thumbnails ----

    def _pixmap_for(self, row) -> QPixmap:
        key = f"thumb:{row['content_hash']}"
        cached = QPixmapCache.find(key)
        if cached:
            return cached

        src = self._root / row["rel_path"]
        if row["missing_since"] is None and can_preview(src):
            path = self._pipeline.get_or_request(row["id"], src, row["content_hash"])
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    # FIT: a célula tem ICON px; entregar 256px fazia a view
                    # CORTAR a imagem (feedback do Rafael). Encaixa inteira.
                    pix = pix.scaled(
                        ICON, ICON, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
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
        # Multi-seleção (Ctrl/Shift) para agrupar assets à mão — Fatia 6
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        # Rolagem suave: por pixel (o padrão pula uma CÉLULA inteira de
        # 200px por passo, o que fica rápido demais — feedback do Rafael)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)  # px por passo da rodinha
        # Arrastar assets para a árvore de tags (Fatia 8)
        self.setDragEnabled(True)
        self.setDragDropMode(QListView.DragDropMode.DragOnly)
