"""O primeiro `QStyledItemDelegate` do projeto: como cada card da grade é
desenhado (Fatia 27, F4).

Contrato que NÃO pode mudar (senão a grade perde performance ou comportamento
já testado): `sizeHint()` devolve exatamente `CELL`; a view continua com
`uniformItemSizes`, `LayoutMode.SinglePass` e `Movement.Static`. Tudo aqui é
pré-computado no `__init__` — zero alocação de fonte/cor por `paint()`.

Estilo do card, pedido do Rafael: sem cor por tipo de asset (era
`TYPE_COLORS`, saturado) — o reconhecimento do tipo vira um CHIP de texto no
canto com a extensão real (`.FBX`, `.EXR`...), estilo Connecter.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from assetdeck.ui import icons, theme
from assetdeck.ui.asset_grid import (
    CARD_GAP,
    CARD_MARGIN,
    CARD_PAD,
    CELL,
    EXT_ROLE,
    HAS_THUMB_ROLE,
    HIDDEN_ROLE,
    MAX_ICON,
    MIN_ICON,
    NAME_HEIGHT,
    STARRED_ROLE,
    cell_for_icon,
)

_BADGE = 20              # lado do selo (estrela / oculto)
_RADIUS = theme.RADII[theme.DEFAULT.radius][1]     # 8px — o mesmo do resto do tema
_BADGE_BG = QColor(0, 0, 0, 140)   # fundo dos selos sobre a miniatura


class AssetCardDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._font_name = QFont()
        self._font_name.setPixelSize(12)  # px, não pt: mais previsível entre telas
        self._fm_name = QFontMetrics(self._font_name)

        self._font_chip = QFont()
        self._font_chip.setPixelSize(10)
        self._font_chip.setBold(True)
        self._fm_chip = QFontMetrics(self._font_chip)

        self._pen_name = QPen(QColor(theme.TEXT))
        self._pen_chip = QPen(QColor("#FFFFFF"))

        self._brush_surface = QColor("#FFFFFF")
        self._brush_hover = QColor(theme.blend(theme.HOVER, "#FFFFFF"))
        self._brush_selected = QColor(theme.blend(theme.SELECTION, "#FFFFFF"))
        self._pen_border = self._qcolor(theme.BORDER)
        self._pen_selected_border = QColor(theme.ACCENT)

        self._icon_star = icons.pixmap("star-filled", "#FFFFFF", 12)
        self._icon_hidden = icons.pixmap("eye-off", "#FFFFFF", 12)

        self._cell = CELL  # tamanho devolvido por sizeHint(); ver set_icon_size

    @staticmethod
    def _qcolor(rgba: tuple[int, int, int, float]) -> QColor:
        r, g, b, a = rgba
        c = QColor(r, g, b)
        c.setAlphaF(a)
        return c

    def set_icon_size(self, px: int) -> None:
        """Chamado pela AssetGridView quando o slider de tamanho muda."""
        px = max(MIN_ICON, min(MAX_ICON, px))
        self._cell = cell_for_icon(px)

    # ---- Qt ----

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return self._cell

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card_rect = option.rect.adjusted(
            CARD_MARGIN, CARD_MARGIN, -CARD_MARGIN, -CARD_MARGIN
        )
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.setBrush(self._brush_selected)
            painter.setPen(QPen(self._pen_selected_border, 1.5))
        else:
            painter.setBrush(self._brush_hover if hover else self._brush_surface)
            painter.setPen(self._pen_border)
        painter.drawRoundedRect(QRectF(card_rect), _RADIUS, _RADIUS)

        # Miniatura sempre QUADRADA (pedido do Rafael: "sem achatar nada") —
        # o lado vem da LARGURA do card, que é o que cell_for_icon() garante
        # bater exatamente com o tamanho que o modelo escalou a imagem para.
        lado = card_rect.width() - 2 * CARD_PAD
        thumb_rect = QRect(card_rect.x() + CARD_PAD, card_rect.y() + CARD_PAD, lado, lado)
        self._paint_thumb(painter, index, thumb_rect)

        name_rect = QRect(
            card_rect.x() + CARD_PAD, thumb_rect.bottom() + CARD_GAP,
            card_rect.width() - 2 * CARD_PAD, NAME_HEIGHT,
        )
        self._paint_name(painter, index, name_rect)

        painter.restore()

    # ---- miolo ----

    def _paint_thumb(self, painter: QPainter, index, rect: QRect) -> None:
        # ORDEM IMPORTA: HAS_THUMB_ROLE só fica correto DEPOIS que
        # DecorationRole rodou nesta mesma pintura (é _pixmap_for, chamado
        # por DecorationRole, quem marca "isto é placeholder ou não" no
        # modelo — ver asset_grid.py). Pedir na ordem trocada lia sempre o
        # valor da pintura ANTERIOR (ou o padrão "sem miniatura" na primeira).
        pix = index.data(Qt.ItemDataRole.DecorationRole)
        has_thumb = bool(index.data(HAS_THUMB_ROLE))

        if has_thumb and pix is not None and not pix.isNull():
            # Rede de segurança: o modelo já escala para caber, mas se algum
            # dia sair de sincronia (ex.: o slider muda no meio de um paint),
            # NUNCA deixa a imagem vazar por cima do nome — encolhe aqui.
            if pix.width() > rect.width() or pix.height() > rect.height():
                pix = pix.scaled(
                    rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            x = rect.x() + (rect.width() - pix.width()) // 2
            y = rect.y() + (rect.height() - pix.height()) // 2
            painter.drawPixmap(x, y, pix)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.TYPE_TINT))
            painter.drawRoundedRect(QRectF(rect), _RADIUS - 2, _RADIUS - 2)

        if bool(index.data(HIDDEN_ROLE)):
            self._badge(painter, rect.x() + 4, rect.y() + 4, self._icon_hidden)
        if bool(index.data(STARRED_ROLE)):
            self._badge(painter, rect.right() - _BADGE - 4, rect.y() + 4, self._icon_star)

        ext = index.data(EXT_ROLE)
        if ext:
            self._chip(painter, rect, ext)

    def _badge(self, painter: QPainter, x: int, y: int, glyph) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BADGE_BG)
        painter.drawRoundedRect(QRectF(x, y, _BADGE, _BADGE), 6, 6)
        gx = x + (_BADGE - glyph.width()) // 2
        gy = y + (_BADGE - glyph.height()) // 2
        painter.drawPixmap(gx, gy, glyph)

    def _chip(self, painter: QPainter, thumb_rect: QRect, texto: str) -> None:
        largura = self._fm_chip.horizontalAdvance(texto) + 10
        altura = self._fm_chip.height() + 3
        x = thumb_rect.x() + 4
        y = thumb_rect.bottom() - altura - 4
        rect = QRectF(x, y, largura, altura)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BADGE_BG)
        painter.drawRoundedRect(rect, 4, 4)

        painter.setFont(self._font_chip)
        painter.setPen(self._pen_chip)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)

    def _paint_name(self, painter: QPainter, index, rect: QRect) -> None:
        """Nome em até 2 linhas, CENTRALIZADO no espaço reservado — pedido do
        Rafael: um nome curto de 1 linha não deve ficar colado no topo com o
        resto do espaço vazio embaixo."""
        nome = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.setFont(self._font_name)
        painter.setPen(self._pen_name)
        painter.setClipRect(rect)  # nunca vaza pra baixo do card em nomes longos
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, nome
        )
        painter.setClipping(False)
