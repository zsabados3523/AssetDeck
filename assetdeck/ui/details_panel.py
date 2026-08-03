"""Painel de detalhes do asset selecionado + abrir pasta/arquivo."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.thumbs.raster import can_thumbnail
from assetdeck.ui import tag_icons, theme

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
    preview_add_requested = Signal(int)   # asset_id (botão 'Adicionar…')
    preview_cover_requested = Signal(int)  # preview_id
    preview_remove_requested = Signal(int)  # preview_id
    property_value_changed = Signal(int, int, object)  # asset_id, property_id, valor
    manage_properties_requested = Signal()  # botão 'Gerenciar propriedades…'
    check_textures_requested = Signal(int, str)  # asset_id, caminho absoluto (Fatia 40)

    def __init__(self, library_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._root = library_root
        self._current: Path | None = None
        self._current_asset_id: int | None = None
        self._loaded_notes: str = ""

        # Subclasse de QWidget filha IGNORA o `background` do QSS sem isto
        # (medido na Fatia 24) — sem ele o painel fica transparente sobre o
        # que estiver atrás em vez de virar o cartão branco.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("card")

        self.preview = QLabel("Selecione um asset")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(220, 220)

        self.name = QLabel("—")
        self.name.setWordWrap(True)
        self.name.setObjectName("title")

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
        # Só faz sentido pra .blend (Fatia 40) — os outros formatos de
        # modelo (.fbx/.obj/.rvt/.skp/.usd*/.abc, Fatia 37) não têm esse
        # conceito de textura religável por caminho dentro do arquivo.
        self.check_textures_btn = QPushButton("Checar texturas…")
        self.check_textures_btn.clicked.connect(self._request_check_textures)
        self._set_buttons(False)

        # Galeria de previews (Fatia 10): thumbs horizontais + capa
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QListWidget

        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setFlow(QListWidget.Flow.LeftToRight)
        self.gallery.setIconSize(QSize(56, 56))
        self.gallery.setFixedHeight(84)
        self.gallery.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._gallery_menu)
        self.add_preview_btn = QPushButton("Adicionar preview…")
        self.add_preview_btn.clicked.connect(self._request_add_preview)

        # Rating (5 estrelas clicáveis) + favorito — Fatia 9
        from PySide6.QtWidgets import QHBoxLayout as _QHBox

        # Ícone, não texto: nenhuma fonte da máquina tem o glifo ★ (medido com
        # QRawFont na Fatia 24) — o Qt caía numa fonte substituta e saía torto.
        from PySide6.QtCore import QSize as _QSize

        from assetdeck.ui import icons as _icons

        self._star_filled = _icons.icon("star-filled", theme.current_colors()["accent"])
        self._star_outline = _icons.icon("star-outline", theme.current_colors()["text_muted"])

        self._rating: int | None = None
        stars_row = _QHBox()
        self.star_btns: list[QPushButton] = []
        for i in range(1, 6):
            b = QPushButton()
            b.setObjectName("ghost")
            b.setIconSize(_QSize(16, 16))
            b.setMaximumWidth(28)
            b.clicked.connect(lambda _c=False, n=i: self._on_star_clicked(n))
            self.star_btns.append(b)
            stars_row.addWidget(b)
        self.fav_btn = QPushButton("Favorito")
        self.fav_btn.setIconSize(_QSize(16, 16))
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self._on_fav_toggled)
        stars_row.addWidget(self.fav_btn)
        stars_row.addStretch()

        # Aviso de edição em massa (sugestão do Rafael): com N selecionados,
        # tag/nota de estrela/favorito valem para todos
        self.multi_label = QLabel()
        self.multi_label.setObjectName("multiWarn")
        self.multi_label.setVisible(False)

        # Tags com checkbox (forma 2 de taggear): marcar/desmarcar aplica na hora
        from PySide6.QtWidgets import QTreeWidget

        tags_label = QLabel("TAGS")
        tags_label.setObjectName("sectionTitle")
        self.tags_tree = QTreeWidget()
        self.tags_tree.setHeaderHidden(True)
        self.tags_tree.setMaximumHeight(150)
        self.tags_tree.itemChanged.connect(self._on_tag_item_changed)
        self._loading_tags = False

        # Custom properties (EAV tipado) — Fatia 22
        props_label = QLabel("PROPRIEDADES")
        props_label.setObjectName("sectionTitle")
        self.props_form = QFormLayout()
        self.manage_props_btn = QPushButton("Gerenciar propriedades…")
        self.manage_props_btn.clicked.connect(self.manage_properties_requested.emit)

        notes_label = QLabel("NOTAS")
        notes_label.setObjectName("sectionTitle")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Anotações suas sobre este asset…")
        self.notes_edit.setMaximumHeight(110)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.save_notes_btn = QPushButton("Salvar nota")
        self.save_notes_btn.setEnabled(False)
        self.save_notes_btn.clicked.connect(self._save_notes)

        # O painel inteiro (preview + form + galeria + tags + propriedades +
        # notas) empilhado sem rolagem fazia a JANELA exigir ~1000px de
        # altura mínima só para caber este painel — o Rafael relatou que o
        # app não redimensionava nem maximizava por causa disso. A correção
        # é rolar o CONTEÚDO aqui dentro, não encolher nenhum widget.
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(self.preview)
        layout.addWidget(self.name)
        layout.addLayout(form)
        layout.addWidget(self.open_folder_btn)
        layout.addWidget(self.open_file_btn)
        layout.addWidget(self.check_textures_btn)
        layout.addLayout(stars_row)
        layout.addWidget(self.multi_label)
        gallery_label = QLabel("GALERIA DE PREVIEWS")
        gallery_label.setObjectName("sectionTitle")
        layout.addWidget(gallery_label)
        layout.addWidget(self.gallery)
        layout.addWidget(self.add_preview_btn)
        layout.addWidget(tags_label)
        layout.addWidget(self.tags_tree)
        layout.addWidget(props_label)
        layout.addLayout(self.props_form)
        layout.addWidget(self.manage_props_btn)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_edit)
        layout.addWidget(self.save_notes_btn)
        layout.addStretch()

        from PySide6.QtWidgets import QFrame, QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # O viewport da QScrollArea preenche o próprio fundo (palette Base,
        # branco opaco) por padrão — cobre os cantos arredondados do #card
        # por baixo dele (bug visto na tela: o painel de detalhes inteiro
        # parecia quadrado). QSS não alcança o viewport de forma confiável
        # (é um QWidget anônimo, sem objectName, criado pelo próprio Qt);
        # a saída certa é desligar o preenchimento automático direto aqui.
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(content)
        content.setAutoFillBackground(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(0)
        outer.addWidget(scroll)

        self._paint_stars()
        self.fav_btn.setIcon(self._star_outline)

    def _set_buttons(self, enabled: bool, path: Path | None = None) -> None:
        self.open_folder_btn.setEnabled(enabled)
        self.open_file_btn.setEnabled(enabled)
        # "Checar texturas…" só faz sentido pra .blend (Fatia 40) — os
        # outros formatos de modelo não têm textura religável por
        # caminho dentro do próprio arquivo.
        e_blend = enabled and path is not None and path.suffix.lower() == ".blend"
        self.check_textures_btn.setVisible(e_blend)

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
        self._set_buttons(not sumido, path)

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

    # ---- galeria de previews ----

    def load_gallery(self, previews: list) -> None:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QListWidgetItem

        self.gallery.clear()
        for p in previews:
            pix = QPixmap(p["file_path"])
            item = QListWidgetItem()
            if not pix.isNull():
                item.setIcon(QIcon(pix.scaled(
                    56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)))
            item.setText("capa" if p["is_cover"] else "")
            item.setData(32, p["id"])
            self.gallery.addItem(item)
        self.gallery.setVisible(bool(previews))

    def _gallery_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu

        item = self.gallery.itemAt(pos)
        if item is None:
            return
        pid = item.data(32)
        menu = QMenu(self)
        menu.addAction("Definir como capa",
                       lambda: self.preview_cover_requested.emit(pid))
        menu.addAction("Remover da galeria",
                       lambda: self.preview_remove_requested.emit(pid))
        menu.exec(self.gallery.mapToGlobal(pos))

    def _request_add_preview(self) -> None:
        if self._current_asset_id is not None:
            self.preview_add_requested.emit(self._current_asset_id)

    # ---- rating / favorito ----

    def set_multi_count(self, n: int) -> None:
        """n>1: avisa que as edições valem para todos os selecionados."""
        self.multi_label.setText(f"⚠ Editando {n} assets selecionados de uma vez")
        self.multi_label.setVisible(n > 1)

    def refresh_theme(self) -> None:
        """Reconstrói os ícones de estrela com a cor do modo atual (Fatia
        43) e redesenha o estado atual de nota/favorito com eles."""
        from assetdeck.ui import icons as _icons

        self._star_filled = _icons.icon("star-filled", theme.current_colors()["accent"])
        self._star_outline = _icons.icon("star-outline", theme.current_colors()["text_muted"])
        self._paint_stars()
        self.fav_btn.setIcon(self._star_filled if self.fav_btn.isChecked() else self._star_outline)

    def _paint_stars(self) -> None:
        for i, b in enumerate(self.star_btns, start=1):
            b.setIcon(
                self._star_filled if self._rating and i <= self._rating
                else self._star_outline
            )

    def load_rating(self, rating: int | None, starred: bool) -> None:
        self._rating = rating
        self._paint_stars()
        self.fav_btn.blockSignals(True)
        self.fav_btn.setChecked(starred)
        self.fav_btn.setIcon(self._star_filled if starred else self._star_outline)
        self.fav_btn.blockSignals(False)

    def _on_star_clicked(self, n: int) -> None:
        # Clicar na estrela da nota atual limpa a nota
        self._rating = None if self._rating == n else n
        self._paint_stars()
        self.rating_changed.emit(self._rating)

    def _on_fav_toggled(self, checked: bool) -> None:
        self.fav_btn.setIcon(self._star_filled if checked else self._star_outline)
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
            item.setIcon(0, QIcon(tag_icons.pixmap_for(r["icon"], r["color"])))
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

    # ---- custom properties (EAV tipado, Fatia 22) ----

    def load_properties(self, defs: list, values: dict[int, object]) -> None:
        """Reconstrói a seção com uma linha por definição ativa. O valor
        inicial é posto ANTES de conectar o sinal — assim popular a tela
        nunca dispara `property_value_changed` sozinho."""
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QCheckBox, QDateEdit, QDoubleSpinBox, QLineEdit

        while self.props_form.rowCount():
            self.props_form.removeRow(0)

        for d in defs:
            pid = d["id"]
            valor = values.get(pid)
            vtype = d["value_type"]
            if vtype == "text":
                w = QLineEdit(str(valor) if valor is not None else "")
                w.editingFinished.connect(
                    lambda pid=pid, w=w: self._emit_property(pid, w.text())
                )
            elif vtype == "number":
                w = QDoubleSpinBox()
                w.setRange(-1_000_000_000, 1_000_000_000)
                w.setDecimals(4)
                w.setValue(float(valor) if valor is not None else 0.0)
                w.editingFinished.connect(
                    lambda pid=pid, w=w: self._emit_property(pid, w.value())
                )
            elif vtype == "bool":
                w = QCheckBox()
                w.setChecked(bool(valor))
                w.toggled.connect(
                    lambda checked, pid=pid: self._emit_property(pid, int(checked))
                )
            else:  # date
                w = QDateEdit()
                w.setCalendarPopup(True)
                w.setDisplayFormat("yyyy-MM-dd")
                w.setDate(QDate.fromString(valor, "yyyy-MM-dd") if valor
                          else QDate.currentDate())
                w.dateChanged.connect(
                    lambda date, pid=pid: self._emit_property(pid, date.toString("yyyy-MM-dd"))
                )
            self.props_form.addRow(f"{d['name']}:", w)

    def _emit_property(self, property_id: int, value) -> None:
        if self._current_asset_id is not None:
            self.property_value_changed.emit(self._current_asset_id, property_id, value)

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

    def _request_check_textures(self) -> None:
        if self._current and self._current_asset_id is not None:
            self.check_textures_requested.emit(self._current_asset_id, str(self._current))
