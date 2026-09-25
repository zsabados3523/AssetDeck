"""Painel de detalhes do asset selecionado + abrir pasta/arquivo."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.thumbs.raster import can_thumbnail
from assetdeck.ui import categories, tag_icons, theme

log = logging.getLogger(__name__)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


class _RotuloElidido(QLabel):
    """QLabel que ENCOLHE: guarda o texto inteiro e DESENHA elidido.

    Existe porque um `QLabel` comum deixa o conteúdo ditar a largura mínima
    do layout — com `wordWrap` ela vira a largura da maior PALAVRA, e sem
    `wordWrap` vira a linha inteira. Os nomes da biblioteca do Rafael são
    tokens sem espaço ("MT_PM_V139_Cortaderia_selloana_pumila_01_01"), então
    o nome exigia 349px e o caminho 284px num painel cujo miolo tem 272px:
    o conteúdo ficava 89px mais largo que o painel e era CORTADO — ele
    relatou como "a janela de detalhes não aparece por completo".

    Elidir o TEXTO (o que a Fatia 79 fazia) não resolve, porque o resultado
    da elisão volta a ser a largura mínima do rótulo — e cada mudança de
    largura reelide, o que também explica o "flickando". Aqui o texto nunca
    muda: quem elide é o `paintEvent`, e `minimumSizeHint` é fixo. Sem
    realimentação entre conteúdo e layout, não há oscilação.
    """

    def __init__(self, modo: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
                 parent=None) -> None:
        super().__init__(parent)
        self._modo = modo
        self.setTextFormat(Qt.TextFormat.PlainText)

    def setText(self, texto: str) -> None:  # noqa: N802
        super().setText(texto)
        # O texto inteiro fica sempre alcançável, mesmo cortado na tela.
        self.setToolTip(texto)

    def minimumSizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize

        return QSize(40, super().minimumSizeHint().height())

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize

        return QSize(40, super().sizeHint().height())

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        rect = self.contentsRect()
        texto = self.fontMetrics().elidedText(self.text(), self._modo, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment()), texto)


class _Secao(QWidget):
    """Bloco colapsável do painel de detalhes (Fatia 79).

    O painel empilhava seis blocos SEMPRE abertos: a rolagem passava de duas
    telas e as ações do topo saíam de vista antes do fim. Agora cada bloco
    abre e fecha, e o estado sobrevive entre sessões (ver
    `secoes_expandidas`/`restaurar_secoes`, gravadas junto do resto do layout
    pela `MainWindow`).

    O cabeçalho é um `QWidget` clicável, não um `QToolButton`: precisa de
    seta à esquerda, título no meio e CONTADOR à direita — três coisas com
    alinhamentos diferentes, que um botão comum não posiciona. O contador é o
    que faz fechar valer a pena: dá pra saber que existem 3 tags sem abrir.
    """

    alternada = Signal()

    def __init__(self, titulo: str, chave: str, *, aberta: bool = True,
                 parent=None) -> None:
        super().__init__(parent)
        self.chave = chave
        self._aberta = aberta

        self._seta = QLabel()
        self._seta.setFixedWidth(12)
        self._titulo = QLabel(titulo.upper())
        self._titulo.setObjectName("secTitulo")
        self._contador = QLabel()
        self._contador.setObjectName("secContador")
        self._contador.setVisible(False)

        self._cabecalho = QWidget()
        self._cabecalho.setObjectName("secHeader")
        self._cabecalho.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cabecalho.setCursor(Qt.CursorShape.PointingHandCursor)
        ch = QHBoxLayout(self._cabecalho)
        ch.setContentsMargins(6, 5, 6, 5)
        ch.setSpacing(6)
        ch.addWidget(self._seta)
        ch.addWidget(self._titulo)
        ch.addStretch(1)
        ch.addWidget(self._contador)
        self._cabecalho.mouseReleaseEvent = self._clique

        self.corpo = QWidget()
        self._corpo_layout = QVBoxLayout(self.corpo)
        self._corpo_layout.setContentsMargins(6, 0, 0, 8)
        self._corpo_layout.setSpacing(6)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._cabecalho)
        raiz.addWidget(self.corpo)

        self.corpo.setVisible(aberta)
        self.refresh_theme()

    # ---- API ----

    def add(self, item) -> None:
        """Aceita widget ou layout — as seções têm dos dois."""
        from PySide6.QtWidgets import QLayout

        if isinstance(item, QLayout):
            self._corpo_layout.addLayout(item)
        else:
            self._corpo_layout.addWidget(item)

    def set_contador(self, n: int | None) -> None:
        """`None` esconde o contador (seções que não contam nada)."""
        if n is None:
            self._contador.setVisible(False)
            return
        self._contador.setText(str(n))
        self._contador.setVisible(True)

    def esta_aberta(self) -> bool:
        return self._aberta

    def set_aberta(self, aberta: bool) -> None:
        self._aberta = bool(aberta)
        self.corpo.setVisible(self._aberta)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """A seta é tingida à mão (não passa pelo QSS), então precisa ser
        refeita quando o modo claro/escuro troca — mesmo padrão do favorito
        aqui do lado."""
        from assetdeck.ui import icons as _icons

        nome = "chevron-down" if self._aberta else "chevron-right"
        self._seta.setPixmap(
            _icons.pixmap(nome, theme.current_colors()["text_muted"], 11))

    # ---- interno ----

    def _clique(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_aberta(not self._aberta)
            self.alternada.emit()


class DetailsPanel(QWidget):
    notes_saved = Signal(int, str)        # asset_id, texto da nota
    tag_toggled = Signal(int, int, bool)  # asset_id, tag_id, marcado?
    starred_changed = Signal(bool)
    preview_add_requested = Signal(int)   # asset_id (botão 'Adicionar…')
    preview_cover_requested = Signal(int)  # preview_id
    preview_remove_requested = Signal(int)  # preview_id
    property_value_changed = Signal(int, int, object)  # asset_id, property_id, valor
    manage_properties_requested = Signal()  # botão 'Gerenciar propriedades…'
    check_textures_requested = Signal(int, str)  # asset_id, caminho absoluto (Fatia 40)
    aviso = Signal(str)                   # recado pro rodapé (Fatia 100)

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
        self.setObjectName("inspectorPanel")

        # Moldura da miniatura (Fatia 48). Era um QLabel solto: sem asset
        # selecionado sobrava um buraco de 220px de altura no topo do painel,
        # com um texto boiando no meio e nada dizendo que ali é o lugar da
        # imagem. Agora é uma pastilha com fundo e contorno próprios — cheia
        # ou vazia, o bloco existe.
        self.preview = QLabel("Selecione um asset")
        self.preview.setObjectName("previewTile")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(72, 72)

        # Elidido à DIREITA: o começo do nome é o que identifica o asset.
        self.name = _RotuloElidido(Qt.TextElideMode.ElideRight)
        self.name.setText("—")
        self.name.setObjectName("title")

        self.f_type = QLabel("—")
        self.f_dims = QLabel("—")
        self.f_size = QLabel("—")
        self.f_format = QLabel("—")
        self.f_path = _RotuloElidido(Qt.TextElideMode.ElideMiddle)
        self.f_path.setText("—")


        self.f_type.setObjectName("inspectorCategory")
        self.f_type.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for valor in (self.f_format, self.f_size):
            valor.setObjectName("kvValue")
            valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.inspector_heading = QLabel("DETALHES")
        self.inspector_heading.setObjectName("inspectorHeading")
        overview_text = QVBoxLayout()
        overview_text.setContentsMargins(0, 0, 0, 0)
        overview_text.setSpacing(4)
        overview_text.addWidget(self.name)
        overview_text.addWidget(self.f_type)
        overview_text_widget = QWidget()
        overview_text_widget.setLayout(overview_text)
        overview = QHBoxLayout()
        overview.setContentsMargins(0, 0, 0, 0)
        overview.setSpacing(11)
        overview.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        overview.addWidget(overview_text_widget, 1, Qt.AlignmentFlag.AlignVCenter)
        self._overview_row = QWidget()
        self._overview_row.setLayout(overview)

        # O que sobra na ficha técnica: rótulo apagado à esquerda, valor à
        # direita. O QFormLayout alinhava os dois à esquerda, com o valor
        # começando logo depois do rótulo mais longo — linhas com o valor em
        # posições diferentes, impossíveis de varrer com o olho.
        form = QVBoxLayout()
        form.setSpacing(2)
        for rotulo, campo in (
            ("Formato", self.f_format),
            ("Resolução", self.f_dims),
            ("Tamanho", self.f_size),
            ("Caminho", self.f_path),
        ):
            form.addWidget(self._kv_row(rotulo, campo))

        # Ícone-só e lado a lado do principal (Fatia 79): "Abrir pasta" e
        # "Favorito" não precisavam de uma linha inteira cada. O texto vira
        # tooltip — some da tela, não da interface.
        self.open_folder_btn = QPushButton()
        self.open_folder_btn.setObjectName("acaoIcone")
        self.open_folder_btn.setToolTip("Abrir pasta")
        self.open_folder_btn.setAccessibleName("Abrir pasta")
        # Largura fixa: sem isto o QPushButton reserva a largura mínima de um
        # botão COM TEXTO e sobra um retângulo vazio do lado do "Abrir".
        self.open_folder_btn.setFixedWidth(38)
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.open_file_btn = QPushButton("Abrir")
        # UM botão principal por tela (regra do tema): abrir o arquivo é a
        # ação que se espera de um gerenciador de assets — as outras são
        # apoio.
        self.open_file_btn.setObjectName("primary")
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

        # Favorito — Fatia 9. Nota em estrelas removida na Fatia 62 (pedido
        # do Rafael: só favorito, sem nota) — ficou só o ícone de estrela
        # para o próprio favorito.
        from PySide6.QtCore import QSize as _QSize

        from assetdeck.ui import icons as _icons

        self._star_filled = _icons.icon("star-filled", theme.current_colors()["accent"])
        self._star_outline = _icons.icon("star-outline", theme.current_colors()["text_muted"])

        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName("acaoIcone")
        self.fav_btn.setToolTip("Favorito")
        self.fav_btn.setAccessibleName("Favorito")
        self.fav_btn.setIconSize(_QSize(16, 16))
        self.fav_btn.setFixedWidth(38)   # mesmo motivo do "Abrir pasta"
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self._on_fav_toggled)

        # Aviso de edição em massa (sugestão do Rafael): com N selecionados,
        # tag/nota de estrela/favorito valem para todos
        self.multi_label = QLabel()
        self.multi_label.setObjectName("multiWarn")
        self.multi_label.setWordWrap(True)  # senão força a largura do painel
        self.multi_label.setVisible(False)

        # Tags com checkbox (forma 2 de taggear): marcar/desmarcar aplica na hora
        from PySide6.QtWidgets import QTreeWidget

        self.tags_tree = QTreeWidget()
        self.tags_tree.setHeaderHidden(True)
        self.tags_tree.setMaximumHeight(150)
        self.tags_tree.itemChanged.connect(self._on_tag_item_changed)
        self._loading_tags = False

        # Custom properties (EAV tipado) — Fatia 22
        self.props_form = QFormLayout()
        self.manage_props_btn = QPushButton("Gerenciar propriedades…")
        self.manage_props_btn.clicked.connect(self.manage_properties_requested.emit)

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
        # A margem da direita reserva espaço para a barra de rolagem (12px no
        # tema). Estava em 8 e a barra passava por cima do fim dos botões.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        layout.addWidget(self.inspector_heading)
        layout.addWidget(self._overview_row)

        # Linha de ação: principal + dois ícones. Antes eram QUATRO botões de
        # largura cheia empilhados — a hierarquia sumia porque todos tinham o
        # mesmo peso na tela.
        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        acoes.setContentsMargins(0, 0, 0, 0)
        acoes.addWidget(self.open_file_btn, 1)
        acoes.addWidget(self.open_folder_btn)
        acoes.addWidget(self.fav_btn)
        self._acoes_row = QWidget()
        self._acoes_row.setLayout(acoes)
        layout.addWidget(self._acoes_row)
        layout.addWidget(self.multi_label)

        # As seções, na ordem em que o Rafael aprovou no mockup. As duas
        # primeiras nascem abertas: são as que ele consulta sempre. O estado
        # real vem de `restaurar_secoes()` na abertura do app.
        self.sec_ficha = _Secao("Ficha técnica", "ficha", aberta=True)
        self.sec_ficha.add(form)

        self.sec_tags = _Secao("Tags", "tags", aberta=True)
        self.sec_tags.add(self.tags_tree)

        self.sec_galeria = _Secao("Galeria de previews", "galeria", aberta=False)
        self.sec_galeria.add(self.gallery)
        self.sec_galeria.add(self.add_preview_btn)

        self.sec_props = _Secao("Propriedades", "props", aberta=False)
        self.sec_props.add(self.props_form)
        self.sec_props.add(self.manage_props_btn)

        self.sec_notas = _Secao("Notas", "notas", aberta=False)
        self.sec_notas.add(self.notes_edit)
        self.sec_notas.add(self.save_notes_btn)

        # "Checar texturas" só existe pra .blend, então não merece espaço fixo
        # na vista principal — vira manutenção, fechada por padrão.
        self.sec_manutencao = _Secao("Manutenção", "manutencao", aberta=False)
        self.sec_manutencao.add(self.check_textures_btn)

        self._secoes = [
            self.sec_ficha, self.sec_tags, self.sec_galeria,
            self.sec_props, self.sec_notas, self.sec_manutencao,
        ]
        for secao in self._secoes:
            layout.addWidget(secao)

        # Pinta os ícones tingidos à mão (pasta, estrela, setas das seções)
        # já na construção — `refresh_theme` existia só pra troca de modo ao
        # vivo, e sem esta chamada o "Abrir pasta" nascia vazio na tela.
        self.refresh_theme()

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
        # NUNCA rolar de lado (Fatia 79): um painel de detalhes tem largura
        # fixa e conteúdo que quebra linha — barra horizontal aqui só aparece
        # quando alguma coisa não coube, e esconder metade de um caminho atrás
        # de uma rolagem lateral é pior do que quebrá-lo em duas linhas. Sem
        # isto, um caminho longo com a árvore de tags aberta fazia a barra
        # surgir e comer altura do painel.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        content.setAutoFillBackground(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 16, 14)
        outer.setSpacing(0)
        outer.addWidget(scroll)

        self.fav_btn.setIcon(self._star_outline)

    @staticmethod
    def _kv_row(rotulo: str, campo: QLabel) -> QWidget:
        """Uma linha da ficha técnica: rótulo apagado à esquerda, valor à
        direita. O valor alinha à direita para os cinco ficarem numa coluna só
        — é o que permite varrer a ficha de cima a baixo sem ler tudo."""
        from PySide6.QtWidgets import QHBoxLayout as _QHBox

        linha = QWidget()
        lay = _QHBox(linha)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        rot = QLabel(rotulo)
        rot.setObjectName("kvLabel")
        campo.setObjectName("kvValue")
        campo.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addWidget(rot)
        # SEM espaçador entre os dois (Fatia 79): o `addStretch` que havia
        # aqui dividia a sobra com o valor, e o rótulo do caminho recebia
        # menos da metade da linha — a elisão comia quase o caminho inteiro
        # ("01 - M...do.jpg" num painel com espaço de sobra). O
        # `AlignRight` do campo já encosta o texto na direita; quem empurra
        # não precisa ser um espaçador.
        lay.addWidget(campo, stretch=1)
        return linha

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
                thumb.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("(sem preview ainda)")

        self.name.setText(row["name"])
        # O `asset_type` cru do banco ("hdri", "pbr_set", "psd") é vocabulário
        # de schema, não de tela — aparecia em minúsculas na ficha. Aqui vira
        # o mesmo rótulo que a barra de categorias usa; tipo desconhecido cai
        # no valor cru em vez de sumir.
        self.f_type.setText(categories.type_label_of(row["asset_type"]))
        self.f_dims.setText(self._read_dims(path))
        self.f_size.setText(human_size(row["size_bytes"]))
        self.f_format.setText(path.suffix.lstrip(".").upper() or "—")
        sumido = row["missing_since"] is not None
        # `_RotuloElidido` guarda o texto inteiro e desenha elidido sozinho —
        # aqui é só atribuir.
        self.f_path.setText(
            f"{row['rel_path']}  ⚠ ARQUIVO SUMIDO" if sumido else row["rel_path"])
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
        self.sec_galeria.set_contador(len(previews))

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

    # ---- favorito ----

    def set_multi_count(self, n: int) -> None:
        """n>1: avisa que as edições valem para todos os selecionados."""
        self.multi_label.setText(f"⚠ Editando {n} assets selecionados de uma vez")
        self.multi_label.setVisible(n > 1)

    # ---- seções colapsáveis (Fatia 79) ----

    def secoes_expandidas(self) -> dict[str, bool]:
        """Estado de abre/fecha, pra `MainWindow` gravar junto do layout."""
        return {s.chave: s.esta_aberta() for s in self._secoes}

    def restaurar_secoes(self, estado: dict) -> None:
        """Reaplica o estado salvo. Chave desconhecida é ignorada de
        propósito: seção renomeada ou removida numa versão futura não pode
        derrubar a restauração do resto do layout."""
        if not isinstance(estado, dict):
            return
        for secao in self._secoes:
            if secao.chave in estado:
                secao.set_aberta(bool(estado[secao.chave]))

    def refresh_theme(self) -> None:
        """Reconstrói os ícones de estrela com a cor do modo atual (Fatia
        43) e redesenha o estado atual de favorito com eles."""
        from assetdeck.ui import icons as _icons

        self._star_filled = _icons.icon("star-filled", theme.current_colors()["accent"])
        self._star_outline = _icons.icon("star-outline", theme.current_colors()["text_muted"])
        self.fav_btn.setIcon(self._star_filled if self.fav_btn.isChecked() else self._star_outline)
        self.open_folder_btn.setIcon(
            _icons.icon("nav-pastas", theme.current_colors()["text_muted"], 16))
        # As setas das seções também são tingidas à mão (Fatia 79).
        for secao in self._secoes:
            secao.refresh_theme()

    def load_starred(self, starred: bool) -> None:
        self.fav_btn.blockSignals(True)
        self.fav_btn.setChecked(starred)
        self.fav_btn.setIcon(self._star_filled if starred else self._star_outline)
        self.fav_btn.blockSignals(False)

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
        # Conta as MARCADAS, não o vocabulário inteiro: a pergunta que o
        # contador responde é "quantas tags ESTE asset tem".
        self.sec_tags.set_contador(len(checked_ids))

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
        self.sec_props.set_contador(len(defs))

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

    def _abrir_no_sistema(self, alvo: Path, oque: str) -> None:
        """Abre `alvo` no gerenciador do sistema, ou DIZ por que não deu.

        Antes isto era um `openUrl` seco (Fatia 100). Quando o arquivo tinha
        sumido do disco, o botão simplesmente não fazia nada — sem aviso, sem
        log, sem pista. Rafael: "não consigo abrir nem abrir o local deles".
        Falha silenciosa é justamente o que as regras do projeto proíbem.
        """
        if not alvo.exists():
            recado = (f"{oque} não existe mais no disco: {alvo}. "
                      "Use Manutenção → Relocalizar se ele só mudou de pasta.")
            log.warning("Tentativa de abrir %s inexistente: %s", oque, alvo)
            self.aviso.emit(recado)
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(alvo))):
            log.error("O sistema recusou abrir %s: %s", oque, alvo)
            self.aviso.emit(f"O sistema não conseguiu abrir {alvo}.")

    def _open_folder(self) -> None:
        if self._current:
            self._abrir_no_sistema(self._current.parent, "a pasta")

    def _open_file(self) -> None:
        if self._current:
            self._abrir_no_sistema(self._current, "o arquivo")

    def _request_check_textures(self) -> None:
        if self._current and self._current_asset_id is not None:
            self.check_textures_requested.emit(self._current_asset_id, str(self._current))
