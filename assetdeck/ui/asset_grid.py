"""Grid virtualizada de assets com thumbnails carregadas de forma preguiçosa.

O modelo devolve placeholder na hora e pede a thumb ao pipeline; quando ela
fica pronta, só aquela célula é redesenhada. Rolar nunca trava.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import Signal

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap, QPixmapCache
from PySide6.QtWidgets import QListView

MIME_ASSETS = "application/x-assetdeck-asset-ids"

from assetdeck.db.repos import assets as assets_repo
from assetdeck.blender.material_preview import preview_key
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.thumbs.preview import can_preview
from assetdeck.ui import theme

log = logging.getLogger(__name__)

# Geometria do card — fonte ÚNICA usada pela view (setGridSize/setIconSize),
# pelo modelo (tamanho real da miniatura) e pelo delegate (sizeHint e o
# retângulo da miniatura em paint()). Antes eram três números fixos que
# podiam sair de sincronia — foi exatamente essa falta de sincronia que
# fazia a miniatura vazar por cima do nome (bug relatado pelo Rafael).
CARD_MARGIN = 3    # respiro entre células, além do spacing(8) da view
CARD_PAD = 10       # margem interna do card, em volta da miniatura
CARD_GAP = 8        # entre a miniatura e o nome
NAME_HEIGHT = 36    # altura reservada para até 2 linhas de nome
MIN_ICON = 96        # menor tamanho de miniatura no slider (Fatia 28)
MAX_ICON = 240        # maior tamanho de miniatura no slider
DEFAULT_ICON = 160


def cell_for_icon(icon_px: int) -> QSize:
    """Tamanho da célula da grade para uma miniatura QUADRADA de `icon_px`.

    A miniatura é sempre quadrada (pedido do Rafael: "sem achatar nada") — é
    o `KeepAspectRatio` no `.scaled()` do modelo quem encaixa a imagem real
    dentro desse quadrado sem esticar.
    """
    largura = icon_px + 2 * CARD_PAD + 2 * CARD_MARGIN
    altura = icon_px + 2 * CARD_PAD + CARD_GAP + NAME_HEIGHT + 2 * CARD_MARGIN
    return QSize(largura, altura)


ICON = DEFAULT_ICON
CELL = cell_for_icon(ICON)

# Papéis extras que o AssetCardDelegate (Fatia 27) lê para desenhar o card.
# Antes o "★ " e o "[oculto] " eram prefixo de string no DisplayRole — além de
# feio, isso quebrava a busca-por-digitação do QListView. Agora DisplayRole
# devolve só o nome, e cada estado vira um papel próprio.
STARRED_ROLE = Qt.ItemDataRole.UserRole + 1
HIDDEN_ROLE = Qt.ItemDataRole.UserRole + 2
TYPE_ROLE = Qt.ItemDataRole.UserRole + 3
EXT_ROLE = Qt.ItemDataRole.UserRole + 4       # ".FBX", ".EXR"... para o chip
HAS_THUMB_ROLE = Qt.ItemDataRole.UserRole + 5  # False = decoração é placeholder
HAS_TAGS_ROLE = Qt.ItemDataRole.UserRole + 6  # True = asset tem 1+ tag (Fatia 61)


class AssetGridModel(QAbstractListModel):
    def __init__(self, conn: sqlite3.Connection, library_root: Path,
                 pipeline: ThumbnailPipeline, library_id: int | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._root = library_root
        # Biblioteca ATIVA (Fatia 69) — não é um filtro que o Rafael
        # escolhe, é o contexto da sessão inteira; restringe a grade sem
        # precisar tocar em set_filters/_current_filters_dict.
        self._library_id = library_id
        self._pipeline = pipeline
        self._pipeline.ready.connect(self._on_thumb_ready)
        self._rows: list[sqlite3.Row] = []
        self._row_by_asset: dict[int, int] = {}
        self._placeholders: dict[tuple[str, int], QPixmap] = {}
        # Populado por _pixmap_for a cada DecorationRole; o delegate lê logo
        # depois via HAS_THUMB_ROLE — mesma chamada de paint, sem corrida.
        self._is_placeholder: dict[int, bool] = {}
        self._material_files: dict[int, tuple[str, dict[str, Path]]] = {}
        # Tamanho da miniatura, ajustável pelo slider da grade (Fatia 28).
        self._icon_px = ICON
        # Filtros ativos (Fatia 4; tipos viraram lista na Fatia 5)
        self._search: str | None = None
        self._asset_types: list[str] = []
        self._category_filters: list[dict] = []  # barra de categorias (Fatia 31)
        self._dir_prefix: str | None = None
        self._include_subdirs: bool = True
        self._expand_sets: bool = False  # toggle 'agrupar' desligado (Fatia 7)
        self._tag_id: int | None = None  # filtro por tag (Fatia 8)
        self._collection_id: int | None = None  # filtro por coleção (Fatia 17)
        self._min_rating: int | None = None       # Fatia 9
        self._starred_only: bool = False
        self._min_resolution: int | None = None
        self._include_hidden: bool = False        # Fatia 10b
        self._include_dependencies: bool = True   # Fatia 13
        self._include_missing: bool = False        # Fatia 100
        self._dominant_color: str | None = None   # Fatia 39
        self._sort_by: str = "name"                # Fatia 63
        self._sort_dir: str = "asc"
        QPixmapCache.setCacheLimit(128 * 1024)  # 128MB de thumbs em RAM

    # ---- dados ----

    def set_filters(self, search: str | None = None, asset_types: list[str] | None = None,
                    dir_prefix: str | None = None, include_subdirs: bool = True,
                    tag_id: int | None = None, min_rating: int | None = None,
                    starred_only: bool = False,
                    min_resolution: int | None = None,
                    include_hidden: bool = False,
                    include_dependencies: bool = True,
                    include_missing: bool = False,
                    collection_id: int | None = None,
                    category_filters: list[dict] | None = None,
                    dominant_color: str | None = None,
                    sort_by: str = "name", sort_dir: str = "asc") -> None:
        self._search = search or None
        self._asset_types = asset_types or []
        self._category_filters = category_filters or []
        self._dir_prefix = dir_prefix or None
        self._include_subdirs = include_subdirs
        self._tag_id = tag_id
        self._min_rating = min_rating
        self._starred_only = starred_only
        self._min_resolution = min_resolution
        self._include_hidden = include_hidden
        self._include_dependencies = include_dependencies
        self._include_missing = include_missing
        self._collection_id = collection_id
        self._dominant_color = dominant_color
        self._sort_by = sort_by
        self._sort_dir = sort_dir
        self._requery()

    def set_expand_sets(self, expand: bool) -> None:
        """Toggle do Rafael: False = sets agrupados (1 card); True = cada mapa
        aparece como card próprio. Só muda a VISUALIZAÇÃO, nunca o banco."""
        if expand != self._expand_sets:
            self._expand_sets = expand
            self._requery()

    def set_icon_size(self, px: int) -> None:
        """Slider de tamanho da grade (Fatia 28). As thumbs já geradas em
        disco não mudam — só o quanto exibimos delas, então basta redesenhar
        (sem re-requisitar nada do pipeline)."""
        px = max(MIN_ICON, min(MAX_ICON, px))
        if px != self._icon_px:
            self._icon_px = px
            if self._rows:
                self.dataChanged.emit(
                    self.index(0), self.index(len(self._rows) - 1),
                    [Qt.ItemDataRole.DecorationRole],
                )

    def reload(self) -> None:
        """Recarga BARATA: só refaz a consulta filtrada (`_requery`).

        Bug de performance achado em 2026-08-05 (Rafael, biblioteca real de
        23 mil assets): isto ANTES também chamava `_warmup()` — que varre a
        biblioteca INTEIRA sem filtro (72 mil linhas no modo expandido) e
        confere no disco se cada thumbnail já existe. Medido: ~1,1s só
        nisso, rodando no thread principal, TRAVANDO a UI — e `reload()` é
        chamado a cada drop de preview, favorito, nota, tag… ações que
        deveriam ser instantâneas. `_warmup()` só faz sentido depois de uma
        VARREDURA (arquivos novos podem ter surgido); ver `warmup_library()`.
        """
        self._requery()

    def warmup_library(self) -> None:
        """Recarga COMPLETA: consulta + pré-aquecimento da biblioteca
        inteira. Chamar só depois de uma varredura real (Reindexar, abrir o
        app) — não a cada mudança pequena (ver `reload()`)."""
        self._requery()
        self._warmup()

    def _requery(self) -> None:
        self.beginResetModel()
        self._material_files.clear()
        self._rows = assets_repo.list_for_grid(
            self._conn, search=self._search, asset_types=self._asset_types,
            dir_prefix=self._dir_prefix, include_subdirs=self._include_subdirs,
            expand_sets=self._expand_sets, tag_id=self._tag_id,
            min_rating=self._min_rating, starred_only=self._starred_only,
            min_resolution=self._min_resolution,
            include_hidden=self._include_hidden,
            include_dependencies=self._include_dependencies,
            include_missing=self._include_missing,
            collection_id=self._collection_id,
            category_filters=self._category_filters,
            dominant_color=self._dominant_color,
            sort_by=self._sort_by, sort_dir=self._sort_dir,
            library_id=self._library_id,
        )
        self._row_by_asset = {r["id"]: i for i, r in enumerate(self._rows)}
        self.endResetModel()
        log.info("Grid: %d assets (filtros: busca=%r tipos=%r pasta=%r subpastas=%s)",
                 len(self._rows), self._search, self._asset_types,
                 self._dir_prefix, self._include_subdirs)

    def _warmup(self) -> None:
        """Gera em background as thumbs da biblioteca TODA — inclusive os
        mapas não-capa dos sets (o modo expandido precisa deles prontos)."""
        # UM `Path` por linha, não dois (Fatia 88). A versão anterior montava
        # o caminho no filtro e de novo na tupla — com as ~143 mil linhas da
        # biblioteca real do Rafael, isso é 286 mil objetos pra usar 127 mil.
        items = []
        for r in assets_repo.list_for_grid(
                self._conn, expand_sets=True, library_id=self._library_id):
            if r["missing_since"] is not None:
                continue
            caminho = self._root / r["rel_path"]
            if not can_preview(caminho):
                continue
            items.append((r["id"], caminho, r["content_hash"]))
        self._pipeline.warmup(items)

    def row_at(self, index: QModelIndex):
        if index.isValid() and 0 <= index.row() < len(self._rows):
            return self._rows[index.row()]
        return None

    def index_of_asset(self, asset_id: int) -> QModelIndex | None:
        """Onde este asset está agora (para restaurar a seleção pós-recarga)."""
        linha = self._row_by_asset.get(asset_id)
        return self.index(linha) if linha is not None else None

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
        if role == STARRED_ROLE:
            return bool(row["starred"])
        if role == HIDDEN_ROLE:
            return bool(row.get("hidden"))
        if role == TYPE_ROLE:
            return row["asset_type"]
        if role == EXT_ROLE:
            return Path(row["rel_path"]).suffix.upper()
        if role == HAS_TAGS_ROLE:
            return bool(row.get("has_tags"))
        if role == HAS_THUMB_ROLE:
            # A pintura sempre pede DecorationRole antes (é o delegate quem
            # decide a ordem), então esta chave já está populada.
            return not self._is_placeholder.get(row["id"], True)
        return None

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return [MIME_ASSETS]

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        """Dados do arrasto — servem para DENTRO e para FORA do AssetDeck.

        - MIME_ASSETS: uso interno (taggear, definir preview)
        - text/uri-list: arrastar para o BLENDER ou qualquer outro app.
          O Blender recebe como arquivo solto e abre o menu nativo dele
          (Open/Append/Link para .blend; importa .fbx/.obj; etc).
        """
        from PySide6.QtCore import QUrl

        linhas = [r for r in (self.row_at(i) for i in indexes) if r]
        ids = sorted({r["id"] for r in linhas})
        mime = QMimeData()
        mime.setData(MIME_ASSETS, ",".join(str(i) for i in ids).encode())

        urls, vistos = [], set()
        for r in linhas:
            if r["missing_since"] is not None:
                continue  # arquivo sumido: não faz sentido arrastar
            caminho = self._root / r["rel_path"]
            if str(caminho) not in vistos:
                vistos.add(str(caminho))
                urls.append(QUrl.fromLocalFile(str(caminho)))
        if urls:
            mime.setUrls(urls)
        return mime

    # ---- thumbnails ----

    def _pixmap_for(self, row) -> QPixmap:
        cover = row.get("cover_path")
        material_path = None
        material_key = None
        if (not cover and not self._expand_sets and row["asset_type"] == "pbr_set"
                and row["missing_since"] is None):
            cached_files = self._material_files.get(row["id"])
            if cached_files is None:
                files = assets_repo.list_files(self._conn, row["id"])
                maps = {}
                for f in files:
                    if f["map_role"]:
                        maps.setdefault(f["map_role"], self._root / f["rel_path"])
                cached_files = (preview_key(files), maps)
                self._material_files[row["id"]] = cached_files
            material_key, maps = cached_files
            if maps:
                material_path = self._pipeline.get_or_request_material(
                    row["id"], row["name"], maps, material_key)

        if cover:
            # Capa escolhida pelo usuário vence o arquivo do asset
            src = Path(cover)
            key_hash = f"prev-{src.stem}"  # nome já é uuid: chave estável
        elif material_path is not None:
            src = material_path
            key_hash = f"material-{material_key}"
        else:
            src = self._root / row["rel_path"]
            key_hash = row["content_hash"]

        # Bug pego na Fatia 27: a chave não incluía o tamanho. Se o tamanho
        # do ícone mudasse (agora pode, via slider — Fatia 28), o
        # QPixmapCache servia pixmaps do tamanho velho pelo resto do processo.
        key = f"thumb:{key_hash}:{self._icon_px}"
        cached = QPixmapCache.find(key)
        if cached:
            self._is_placeholder[row["id"]] = False
            return cached

        if material_path is not None:
            pix = QPixmap(str(material_path))
            if not pix.isNull():
                pix = pix.scaled(
                    self._icon_px, self._icon_px, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                QPixmapCache.insert(key, pix)
                self._is_placeholder[row["id"]] = False
                return pix
            log.warning("Capa PBR ilegível para asset %d: %s", row["id"], material_path)
            src = self._root / row["rel_path"]
            key_hash = row["content_hash"]
            key = f"thumb:{key_hash}:{self._icon_px}"

        if (cover or row["missing_since"] is None) and can_preview(src):
            path = self._pipeline.get_or_request(row["id"], src, key_hash)
            if path is not None:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    # FIT: encaixa inteira dentro do quadrado (sem esticar,
                    # sem cortar — pedido do Rafael); o delegate ainda
                    # reencolhe na hora de pintar se sobrar alguma folga.
                    pix = pix.scaled(
                        self._icon_px, self._icon_px, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    QPixmapCache.insert(key, pix)
                    self._is_placeholder[row["id"]] = False
                    return pix
        self._is_placeholder[row["id"]] = True
        return self._placeholder(row["asset_type"])

    def _on_thumb_ready(self, asset_id: int, _path: str) -> None:
        i = self._row_by_asset.get(asset_id)
        if i is not None:
            idx = self.index(i)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def _placeholder(self, asset_type: str) -> QPixmap:
        """Pastilha lisa na cor única de "sem miniatura" (decisão do Rafael:
        nada de cor por tipo). O reconhecimento do tipo passa a ser o chip de
        extensão que o AssetCardDelegate desenha por cima (Fatia 27).

        Segue `self._icon_px` (não o módulo ICON fixo): o delegate nunca
        desenha este pixmap no tamanho nativo dentro da grade (ele pinta o
        próprio retângulo TYPE_TINT), mas o baralho de arrasto múltiplo
        (`_stacked_preview`) usa `_pixmap_for` — inclusive o fallback — então
        vale manter consistente com o tamanho pedido.
        """
        chave = (asset_type, self._icon_px)
        pix = self._placeholders.get(chave)
        if pix is None:
            pix = QPixmap(self._icon_px, self._icon_px)
            pix.fill(QColor(theme.current_colors()["type_tint"]))
            self._placeholders[chave] = pix
        return pix

    def refresh_theme(self) -> None:
        """Limpa o cache de pastilhas "sem miniatura" (Fatia 43) — elas
        guardam a cor já pintada num QPixmap, então trocar de modo claro/
        escuro precisa esvaziar o cache pra próxima pintura pegar a cor
        certa, em vez de continuar servindo a antiga."""
        self._placeholders.clear()


def _stacked_preview(model: AssetGridModel, rows: list) -> QPixmap:
    """Preview 'baralho de cartas' para arrastar vários assets: até 3
    miniaturas empilhadas (a primeira selecionada por cima) + um selo com
    o total, sempre do mesmo tamanho — não importa a distância entre os
    itens na grade original."""
    thumb = 56
    canvas = QSize(88, 88)
    pix = QPixmap(canvas)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    visiveis = rows[:3]
    for i in reversed(range(len(visiveis))):
        offset = i * 10
        rect = QRect(offset, offset, thumb, thumb)
        painter.setBrush(QColor("white"))
        painter.setPen(QColor("#888888"))
        painter.drawRoundedRect(rect, 6, 6)
        thumb_pix = model._pixmap_for(visiveis[i]).scaled(
            thumb - 6, thumb - 6, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(rect.x() + 3, rect.y() + 3, thumb_pix)

    total = len(rows)
    if total > len(visiveis):
        badge = QRect(canvas.width() - 30, canvas.height() - 20, 30, 20)
        painter.setBrush(QColor("#2b6cb0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge, 9, 9)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"+{total}")

    painter.end()
    return pix


class AssetGridView(QListView):
    # Imagem externa solta sobre um card → vira preview do asset (Fatia 10)
    image_dropped = Signal(int, str)  # asset_id, caminho local da imagem
    # Asset de imagem arrastado DE DENTRO da grid sobre um model (Fatia 10b)
    asset_preview_dropped = Signal(int, list)  # alvo, [asset_ids de origem]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        # CAUSA REAL do bug do card que ficava preso onde o mouse soltou
        # (Fatia 19b): setViewMode(IconMode) liga Movement.Free por padrão,
        # e em Free o Qt deixa o usuário REPOSICIONAR os ícones dentro da
        # grade, guardando a posição nova de cada um. Aqui a grade é sempre
        # ordenada pela consulta (não há reordenar à mão), então Static.
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        # Layout SÍNCRONO: com uniformItemSizes o custo é O(1) (2000 itens
        # recarregam em ~40ms). Em Batched o scrollbar só descobria o tamanho
        # real DEPOIS, e o Qt clampava a rolagem — era a causa da lista pular
        # para cima ao anexar um preview (bug relatado pelo Rafael).
        self.setLayoutMode(QListView.LayoutMode.SinglePass)
        self.setUniformItemSizes(True)
        self.setGridSize(CELL)
        self.setIconSize(QSize(ICON, ICON))
        self.setWordWrap(True)
        self.setSpacing(8)
        self.setMouseTracking(True)  # hover do card (Fatia 27)
        # Import tardio: evita ciclo (o delegate importa CELL/papéis daqui).
        from assetdeck.ui.asset_card_delegate import AssetCardDelegate

        self.setItemDelegate(AssetCardDelegate(self))
        # Card sob o cursor (Fatia 74) — pra avisar o delegate quando muda,
        # ele anima a transição em vez de saltar direto (ver `set_hover`).
        self._hover_index = QModelIndex()
        # Multi-seleção (Ctrl/Shift) para agrupar assets à mão — Fatia 6
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        # Rolagem suave: por pixel (o padrão pula uma CÉLULA inteira de
        # 200px por passo, o que fica rápido demais — feedback do Rafael)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)  # px por passo da rodinha
        # Arrastar assets: para a árvore de tags (F8), sobre outro asset (F10b)
        # e para FORA do app — Blender, gerenciador de arquivos… (F13)
        self.setDragEnabled(True)
        self.setDragDropMode(QListView.DragDropMode.DragDrop)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        # CAUSA REAL de "arrastar imagem pro card parou de funcionar" e do
        # cursor de "bloqueado" (achado em 2026-08-06, regressão da Fatia
        # 19b): `setMovement(Static)` faz, lá dentro do Qt,
        # `viewport()->setAcceptDrops(false)` — ele assume que uma grade
        # imóvel não recebe drop nenhum. E quem recebe os eventos de
        # arrasto do sistema é o VIEWPORT, não a view. `setAcceptDrops(True)`
        # na view só repassa pro viewport quando o valor MUDA (evento
        # AcceptDropsChange); como já estava True, nada era repassado e o
        # viewport ficava recusando tudo — nem `dragEnterEvent` nem
        # `dropEvent` chegavam a disparar (confirmado: zero ocorrências
        # deles em 6 arquivos de log do Rafael). Por isso o viewport é
        # religado AQUI, explicitamente, depois de `setMovement`.
        self.viewport().setAcceptDrops(True)

    # ---- tamanho da miniatura (slider da Fatia 28) ----

    def set_icon_size(self, px: int) -> None:
        """Muda o tamanho das miniaturas ao vivo — grade, modelo e delegate
        têm de mudar JUNTOS (é `cell_for_icon` quem garante isso)."""
        px = max(MIN_ICON, min(MAX_ICON, px))
        cell = cell_for_icon(px)
        self.setIconSize(QSize(px, px))
        self.setGridSize(cell)

        delegate = self.itemDelegate()
        if hasattr(delegate, "set_icon_size"):
            delegate.set_icon_size(px)

        model = self.model()
        if model is not None and hasattr(model, "set_icon_size"):
            model.set_icon_size(px)

        # uniformItemSizes cacheia o tamanho antigo; sem isto a grade só
        # relayouta no próximo scroll/resize.
        self.doItemsLayout()

    # ---- feedback de clique no card (Fatia 74) ----

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """Guarda qual card está com o botão pressionado, pro delegate
        pintar o "afundar" (sombra menor, ver `asset_card_delegate.py`).
        Não dá pra confiar em `QStyle.State_Sunken` vir preenchido sozinho
        num `QListView` customizado — daí rastrear à mão, mesmo raciocínio
        do hover (`setMouseTracking`, já ligado no `__init__`)."""
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.position().toPoint())
            delegate = self.itemDelegate()
            if hasattr(delegate, "set_pressed"):
                delegate.set_pressed(idx)
            self.viewport().update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        delegate = self.itemDelegate()
        if hasattr(delegate, "set_pressed"):
            delegate.set_pressed(None)
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """Avisa o delegate quando o card sob o cursor MUDA (Fatia 74) —
        `setMouseTracking(True)` já liga este evento sem botão pressionado.
        O Qt tem seu próprio rastreio nativo de `State_MouseOver`, mas ele
        não avisa NINGUÉM da troca — só aparece pronto no próximo paint().
        Aqui é o gatilho da animação suave de entrada/saída."""
        super().mouseMoveEvent(event)
        idx = self.indexAt(event.position().toPoint())
        if idx != self._hover_index:
            delegate = self.itemDelegate()
            if hasattr(delegate, "set_hover"):
                delegate.set_hover(self._hover_index, idx)
            self._hover_index = idx

    def leaveEvent(self, event) -> None:  # noqa: N802
        """O cursor pode sair da grade sem passar por cima de outro card —
        sem isto, o último card sob o mouse ficava "hover" pra sempre."""
        super().leaveEvent(event)
        if self._hover_index.isValid():
            delegate = self.itemDelegate()
            if hasattr(delegate, "set_hover"):
                delegate.set_hover(self._hover_index, QModelIndex())
            self._hover_index = QModelIndex()

    def setModel(self, model) -> None:  # noqa: N802
        """Zera o hover a cada reset do modelo (Fatia 74). O progresso da
        animação é indexado por LINHA, e trocar de filtro/pasta faz a linha 7
        virar outro asset — sem isto, um card que nunca viu o mouse podia
        aparecer aceso depois de uma recarga."""
        super().setModel(model)
        if model is not None:
            model.modelReset.connect(self._reset_hover)

    def _reset_hover(self) -> None:
        self._hover_index = QModelIndex()
        delegate = self.itemDelegate()
        if hasattr(delegate, "clear_hover"):
            delegate.clear_hover()

    # ---- arrasto para fora (Tag, Collection, Blender, gerenciador de arquivos) ----

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        """Padrão do Qt: cada item mantém a posição relativa que tinha na
        grade, o que fica esquisito quando os itens selecionados estão
        longe uns dos outros. Com 2+ itens, desenha um preview compacto
        ('baralho' + contador) que acompanha o cursor pelo centro —
        pedido do Rafael depois de usar as coleções (Fatia 17b). Com 1
        item só, o padrão do Qt já fica bom — não mexe.

        A Fatia 51 tinha aqui um FALLBACK que, quando o drop "não chegava",
        olhava onde o cursor estava e aplicava o preview na mão. Ele foi
        REMOVIDO em 2026-08-06, junto com a descoberta da causa real (ver
        `__init__`: o viewport recusava todo drop). Além de desnecessário,
        era perigoso: ele decidia só pela coordenada do cursor, sem saber
        qual JANELA estava por cima nem se o gesto tinha sido cancelado —
        soltar um asset no Blender aberto por cima da grade, ou apertar Esc
        no meio do arrasto, aplicava um preview que ninguém pediu.
        """
        # O drag pega o lugar do mouseReleaseEvent normal (o Qt consome o
        # solto do botão como parte do gesto) — sem isto, o card ficava
        # "afundado" (Fatia 74) depois de um arrasto completo, porque
        # ninguém nunca chamou set_pressed(None).
        delegate = self.itemDelegate()
        if hasattr(delegate, "set_pressed"):
            delegate.set_pressed(None)

        indexes = self.selectedIndexes()
        log.info("startDrag: %d item(ns) selecionado(s)", len(indexes))
        if not indexes:
            return

        model = self.model()
        mime = model.mimeData(indexes)
        if mime is None:
            return

        if len(indexes) < 2:
            super().startDrag(supportedActions)
            log.info("startDrag: super().startDrag() retornou (drag de 1 item encerrado)")
        else:
            rows = [r for r in (model.row_at(i) for i in indexes) if r is not None]
            drag = QDrag(self)
            drag.setMimeData(mime)
            pixmap = _stacked_preview(model, rows)
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
            resultado = drag.exec(supportedActions, Qt.DropAction.CopyAction)
            log.info("startDrag: drag.exec() retornou %s", resultado)
            # Sem isso, às vezes sobrava uma cópia "presa" na tela no lugar
            # onde soltou, em vez do card voltar limpo pro lugar de origem
            # (Fatia 19b) — o QDrag manual não passa pela máquina de estados
            # de repaint que o startDrag padrão do Qt já cuida sozinho.
            self.viewport().update()

    # ---- receber imagem externa como preview ----

    @staticmethod
    def _dropped_image(mime) -> str | None:
        from assetdeck.thumbs.raster import RASTER_EXTS

        # Arrasto que saiu da própria grid não é "imagem externa" —
        # senão arrastar um asset para outro viraria drop de arquivo.
        if mime.hasFormat(MIME_ASSETS) or not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if p.rsplit(".", 1)[-1].lower() in RASTER_EXTS:
                    return p
        return None

    def _apply_drop(self, mime: QMimeData, row) -> bool:
        """Lógica compartilhada entre o dropEvent nativo e o fallback por
        posição do cursor. Retorna True se aplicou algo."""
        path = self._dropped_image(mime)
        if path is not None:
            log.info("_apply_drop: caso imagem externa -> image_dropped(%s)", row["id"])
            self.image_dropped.emit(row["id"], path)
            return True

        if mime.hasFormat(MIME_ASSETS):
            origem = [int(x) for x in bytes(mime.data(MIME_ASSETS)).decode().split(",") if x]
            origem = [i for i in origem if i != row["id"]]  # não sobre si mesmo
            log.info("_apply_drop: caso asset-sobre-asset — alvo=%s origem=%s", row["id"], origem)
            if origem:
                self.asset_preview_dropped.emit(row["id"], origem)
                return True
        return False

    def dropEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        row = self.model().row_at(index) if index.isValid() else None
        # INFO: dispara uma vez por drop — é o ponto que confirma se o
        # gesto chegou até o fim (diagnóstico do bug de preview via drag).
        log.info("dropEvent: pos=%s alvo=%s formats=%s",
                 event.position().toPoint(), row["name"] if row else None,
                 event.mimeData().formats())

        if row is not None and self._apply_drop(event.mimeData(), row):
            event.acceptProposedAction()
            return
        if row is None and self._dropped_image(event.mimeData()) is not None:
            log.info("dropEvent: imagem externa solta fora de um card — ignorado")
            return
        # Sem alvo válido dentro da própria grade — o modelo não suporta
        # reordenar por drop (sem InternalMove), então cair no dropEvent
        # padrão do Qt aqui era um caminho morto que deixava a view com o
        # "fantasma" da miniatura presa onde soltou (Fatia 19b).
        log.info("dropEvent: nenhum caso bateu (row=%s) — ignorando o evento", row)
        event.ignore()
        self.viewport().update()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        # INFO: uma vez por gesto de arrastar que ENTRA nesta view — se isto
        # nunca aparecer no log durante um arrasto que "não faz nada", o
        # problema é anterior a este código (o SO/Qt não está entregando o
        # evento à janela, não é lógica Python).
        log.info("dragEnterEvent: formats=%s hasUrls=%s",
                 event.mimeData().formats(), event.mimeData().hasUrls())
        if self._dropped_image(event.mimeData()) or \
                event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        # DEBUG (não INFO): dispara a cada pixel de movimento durante o
        # arrasto — em INFO inundaria o log em segundos.
        log.debug("dragMoveEvent: pos=%s", event.position().toPoint())
        if self._dropped_image(event.mimeData()) or \
                event.mimeData().hasFormat(MIME_ASSETS):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
