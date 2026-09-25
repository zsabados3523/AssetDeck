"""Preview ampliado (duplo clique no asset — pedido do Rafael).

Mostra a imagem em resolução completa, ajustada à tela. A decodificação do
arquivo original (que pode ter 100MB) acontece em thread — o preview abre
na hora com a thumbnail e troca pela versão cheia quando pronta. Esc ou
clicar fora fecha.

Overlay embutido na janela principal (Fatia 65), não janela separada — ver
`assetdeck.ui.overlay.OverlayPanel`.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.indexer.grouper import PRIMARY_ORDER
from assetdeck.thumbs.preview import can_preview, load_full_image
from assetdeck.ui import pools, theme
from assetdeck.ui.overlay import OverlayPanel

log = logging.getLogger(__name__)


class _Signaller(QObject):
    loaded = Signal(str, QImage, int, int)  # caminho, imagem, largura, altura
    failed = Signal(str, str)  # caminho, erro


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
            self._sig.loaded.emit(str(self._path), qimg, w, h)
        except Exception as exc:
            log.exception("Preview ampliado falhou para %s", self._path)
            self._sig.failed.emit(str(self._path), str(exc))


class PreviewPopup(OverlayPanel):
    def __init__(self, host: QWidget) -> None:
        super().__init__(host)

        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setAccessibleName("Nome do asset visualizado")

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("previewSubtitle")
        self.close_button = QToolButton()
        self.close_button.setObjectName("ghost")
        self.close_button.setText("Fechar")
        self.close_button.setAccessibleName("Fechar preview")
        self.close_button.clicked.connect(self.close_overlay)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setAccessibleName("Preview ampliado do asset")
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.info_label.setObjectName("previewInfo")
        self.info_label.setAccessibleName("Estado do preview")

        self.format_value = QLabel("—")
        self.resolution_value = QLabel("—")
        self.files_value = QLabel("—")
        self.maps_heading = QLabel("MAPAS")
        self.maps_heading.setObjectName("previewSectionTitle")
        self.maps_count = QLabel()
        self.maps_count.setObjectName("previewMapCount")

        # Seletor vertical: cada mapa tem um alvo de clique próprio e a lista
        # não precisa dividir o espaço do palco com uma fileira de pastilhas.
        self.maps_bar = QWidget()
        self.maps_bar.setObjectName("previewMaps")
        self.maps_bar.setAccessibleName("Mapas do material")
        self.maps_bar.setAccessibleDescription(
            "Escolha o material ou um mapa PBR para visualizar")
        self.maps_scroll = QScrollArea()
        self.maps_scroll.setObjectName("previewMapsScroll")
        self.maps_scroll.setWidgetResizable(True)
        self.maps_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.maps_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.maps_scroll.setWidget(self.maps_bar)
        self.maps_scroll.setAccessibleName("Lista rolável de mapas do material")
        self._maps_layout = QVBoxLayout(self.maps_bar)
        self._maps_layout.setContentsMargins(0, 0, 0, 0)
        self._maps_layout.setSpacing(5)
        maps_header = QHBoxLayout()
        maps_header.setContentsMargins(0, 0, 0, 0)
        maps_header.addWidget(self.maps_heading)
        maps_header.addStretch(1)
        maps_header.addWidget(self.maps_count)
        self._maps_layout.addLayout(maps_header)
        self._maps_group = QButtonGroup(self)
        self._maps_group.setExclusive(True)

        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 0, 0, 0)
        header_text.setSpacing(3)
        header_text.addWidget(self.title_label)
        header_text.addWidget(self.subtitle_label)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addLayout(header_text, 1)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

        stage = QWidget()
        stage.setObjectName("previewStage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(12, 12, 12, 10)
        stage_layout.setSpacing(8)
        stage_layout.addWidget(self.image_label, 1)
        stage_layout.addWidget(self.info_label)

        stage_divider = QFrame()
        stage_divider.setObjectName("previewDivider")
        stage_divider.setFrameShape(QFrame.Shape.VLine)
        stage_divider.setFixedWidth(1)

        self.properties_heading = QLabel("PROPRIEDADES")
        self.properties_heading.setObjectName("previewSectionTitle")
        property_layout = QVBoxLayout()
        property_layout.setContentsMargins(0, 0, 0, 0)
        property_layout.setSpacing(4)
        property_layout.addWidget(self.properties_heading)
        property_layout.addWidget(self._meta_row("Formato", self.format_value))
        property_layout.addWidget(self._meta_row("Resolução", self.resolution_value))
        property_layout.addWidget(self._meta_row("Mapas", self.files_value))
        property_layout.addSpacing(8)
        property_layout.addWidget(self.maps_scroll, 1)
        property_layout.addStretch(1)
        property_panel = QWidget()
        property_panel.setObjectName("previewInspector")
        property_panel.setLayout(property_layout)
        property_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        property_panel.setMinimumWidth(224)
        property_panel.setMaximumWidth(272)

        card_inner = QWidget()
        card_layout = QVBoxLayout(card_inner)
        card_layout.setContentsMargins(8, 6, 8, 8)
        card_layout.setSpacing(15)
        card_layout.addLayout(header)
        top_divider = QFrame()
        top_divider.setObjectName("previewDivider")
        top_divider.setFrameShape(QFrame.Shape.HLine)
        top_divider.setFixedHeight(1)
        card_layout.addWidget(top_divider)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(18)
        content.addWidget(stage, 1)
        content.addWidget(stage_divider)
        content.addWidget(property_panel)
        card_layout.addLayout(content, 1)
        self._card = theme.make_card(card_inner, sombra=True)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self._card, 0, Qt.AlignmentFlag.AlignCenter)
        outer.addStretch(1)

        self._sig = _Signaller()
        self._sig.loaded.connect(self._on_loaded)
        self._sig.failed.connect(self._on_failed)
        self._loading_for: Path | None = None
        self._library_root: Path | None = None
        self._material_asset_id: int | None = None
        self._material_preview_path: Path | None = None
        self._material_button: QPushButton | None = None
        self._material_thumb: QPixmap | None = None
        self._material_failed = False
        self._source_pixmap: QPixmap | None = None
        self._asset: dict = {}
        # Tamanho do CARTÃO padronizado (feedback do Rafael): não pula de
        # tamanho trocando de imagem, seja ela 256px ou 8K — só o conteúdo
        # escala. Recalculado a cada abertura a partir do tamanho da janela
        # (antes vinha da tela inteira; agora o preview mora dentro da
        # própria janela, então tem de caber nela).
        self._win_w = 800
        self._win_h = 600

    def _resize_card(self) -> None:
        self._win_w = min(1100, int(self._host.width() * 0.90))
        self._win_h = min(800, int(self._host.height() * 0.90))
        self._card.setFixedSize(self._win_w, self._win_h)

    def show_for(self, row: sqlite3.Row, library_root: Path,
                 thumb: QPixmap | None, maps: list | None = None,
                 material_preview: Path | None = None,
                 material_failed: bool = False) -> None:
        self._resize_card()
        self._asset = dict(row)
        self._library_root = library_root
        self._material_asset_id = self._asset.get("id") if material_preview else None
        self._material_preview_path = material_preview
        self._material_thumb = thumb
        self._material_failed = material_failed
        self.title_label.setText(self._asset.get("name", "Asset"))
        self.subtitle_label.setText(_asset_kind_label(self._asset.get("asset_type")))
        self.format_value.setText(
            Path(self._asset.get("rel_path", "")).suffix.upper().lstrip(".") or "—")
        width = self._asset.get("width")
        height = self._asset.get("height")
        self.resolution_value.setText(
            f"{width} × {height} px" if width and height else "—")

        if thumb and not thumb.isNull():
            self._set_image(thumb)
        else:
            self._source_pixmap = None
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("Sem preview")

        self._build_maps_bar(maps, material_preview)
        self.files_value.setText(str(len(maps or [])))
        if material_preview is not None:
            if material_preview.is_file():
                self._load(material_preview)
            else:
                self._loading_for = None
                self.info_label.setText(self._material_status_text())
            self.open_overlay()
            return

        alvo = library_root / self._asset["rel_path"]
        cover = self._asset.get("cover_path")
        if cover and not can_preview(alvo):
            # Asset sem preview visual (.blend, .pdf…) mas com capa escolhida
            # pelo usuário: o preview mostra a capa em resolução completa
            alvo = Path(cover)
        self._load(alvo)
        self.open_overlay()

    # ---- PBR Material Viewer (sets agrupados) ----

    def _build_maps_bar(self, maps: list | None,
                        material_preview: Path | None = None) -> None:
        for btn in self._maps_group.buttons():
            self._maps_group.removeButton(btn)
            self._maps_layout.removeWidget(btn)
            btn.hide()
            btn.deleteLater()
        self._material_button = None
        if not maps or len(maps) < 2:
            self.maps_scroll.setVisible(False)
            return
        self.maps_count.setText(str(len(maps)))
        if material_preview is not None:
            btn = QPushButton("Material")
            btn.setObjectName("previewMapOption")
            btn.setAccessibleName("Preview do material PBR")
            btn.setCheckable(True)
            btn.clicked.connect(self._on_material_clicked)
            self._maps_group.addButton(btn)
            self._maps_layout.addWidget(btn)
            self._material_button = btn
        ordenados = sorted(
            maps, key=lambda m: PRIMARY_ORDER.index(m["map_role"])
            if m["map_role"] in PRIMARY_ORDER else 99,
        )
        for m in ordenados:
            label = _map_role_label(m["map_role"])
            btn = QPushButton(label)
            btn.setObjectName("previewMapOption")
            btn.setAccessibleName(f"Visualizar mapa {label}")
            btn.setCheckable(True)
            rel = m["rel_path"]
            btn.setToolTip(rel)
            btn.clicked.connect(lambda _c=False, r=rel: self._on_map_clicked(r))
            self._maps_group.addButton(btn)
            self._maps_layout.addWidget(btn)
        self._maps_group.buttons()[0].setChecked(True)
        self.maps_scroll.setVisible(True)

    def _on_map_clicked(self, rel_path: str) -> None:
        if self._library_root is not None:
            self._load(self._library_root / rel_path)

    def _on_material_clicked(self) -> None:
        path = self._material_preview_path
        if path is None:
            return
        if path.is_file():
            self._load(path)
        else:
            self._loading_for = None
            if self._material_thumb and not self._material_thumb.isNull():
                self._set_image(self._material_thumb)
            self.info_label.setText(self._material_status_text())

    def _material_status_text(self) -> str:
        if self._material_failed:
            return "Não consegui gerar o preview do material — escolha um mapa"
        return "Gerando preview do material…"

    def material_preview_ready(self, asset_id: int, path: str) -> None:
        """Atualiza o popup aberto só se este ainda mostra o mesmo material."""
        if (not self.isVisible() or asset_id != self._material_asset_id
                or self._material_preview_path != Path(path)):
            return
        if self._material_button and self._material_button.isChecked():
            self._load(Path(path))

    def material_preview_failed(self, asset_id: int, path: str) -> None:
        if (not self.isVisible() or asset_id != self._material_asset_id
                or self._material_preview_path != Path(path)):
            return
        self._material_failed = True
        if self._material_button and self._material_button.isChecked():
            self.info_label.setText(self._material_status_text())

    def _load(self, path: Path) -> None:
        self._loading_for = path
        if can_preview(path) and path.exists():
            self.info_label.setText("Carregando resolução completa…")
            # Pool interativo, não o global: a prévia não pode ficar atrás
            # da fila de miniaturas (ver `ui/pools.py`).
            pools.interativo().start(_LoadJob(self._sig, path))
        else:
            self.info_label.setText(
                "Preview em resolução completa disponível só para imagens "
                "e HDR/EXR por enquanto — Esc fecha"
            )

    # ---- resultado do carregamento ----

    def _on_loaded(self, path: str, qimg: QImage, w: int, h: int) -> None:
        if self._loading_for != Path(path) or not self.isVisible():
            return
        pix = QPixmap.fromImage(qimg)
        self._set_image(pix)
        self.info_label.setText(f"{w} × {h} px — Esc fecha")

    def _on_failed(self, path: str, message: str) -> None:
        if self._loading_for != Path(path) or not self.isVisible():
            return
        self.info_label.setText(f"Não consegui carregar a imagem completa: {message}")

    def _fit(self, pix: QPixmap) -> QPixmap:
        """Encaixa no palco atual sem ampliar além do tamanho original."""
        area = self.image_label.contentsRect()
        area_w = area.width() if area.width() > 8 else self._win_w - 340
        area_h = area.height() if area.height() > 8 else self._win_h - 160
        return pix.scaled(min(pix.width(), area_w), min(pix.height(), area_h),
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)

    @staticmethod
    def _meta_row(label: str, value: QLabel) -> QWidget:
        caption = QLabel(label)
        caption.setObjectName("previewMetaLabel")
        value.setObjectName("previewMetaValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)
        layout.addWidget(caption)
        layout.addStretch(1)
        layout.addWidget(value)
        row.setFixedHeight(30)
        return row

    def _set_image(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self.image_label.setText("")
        self.image_label.setPixmap(self._fit(pixmap))

    def resizeEvent(self, event) -> None:  # noqa: N802
        if self._source_pixmap is not None and not self._source_pixmap.isNull():
            self.image_label.setPixmap(self._fit(self._source_pixmap))
        super().resizeEvent(event)


def _map_role_label(role: str) -> str:
    """Nome visível de cada mapa, sem expor os identificadores do indexador."""
    return {
        "basecolor": "Base Color",
        "normal": "Normal",
        "roughness": "Roughness",
        "height": "Height",
        "ao": "Oclusão",
        "metallic": "Metallic",
        "specular": "Specular",
        "opacity": "Opacity",
        "emission": "Emission",
        "none": "Arquivo",
    }.get(role, role.replace("_", " ").title())


def _asset_kind_label(asset_type: str | None) -> str:
    return {
        "pbr_set": "Material PBR",
        "model": "Modelo 3D",
        "hdri": "HDRI",
        "texture": "Textura",
        "cutout": "Recorte",
    }.get(asset_type or "", "Asset")
