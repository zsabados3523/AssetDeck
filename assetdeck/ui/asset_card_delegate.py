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
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from assetdeck.ui import icons, theme
from assetdeck.ui.asset_grid import (
    CARD_GAP,
    CARD_MARGIN,
    CARD_PAD,
    CELL,
    EXT_ROLE,
    HAS_TAGS_ROLE,
    HAS_THUMB_ROLE,
    HIDDEN_ROLE,
    MAX_ICON,
    MIN_ICON,
    NAME_HEIGHT,
    STARRED_ROLE,
    cell_for_icon,
)

_BADGE = 20              # lado do selo (estrela / oculto)
_BADGE_BG = QColor(0, 0, 0, 140)   # fundo dos selos sobre a miniatura

# Espessura do contorno em cada estado (Fatia 47). O card em repouso quase não
# tem contorno — quem separa um card do outro é o espaçamento. O contorno é
# reservado para RESPONDER ao mouse: é ele que engorda no hover e vira destaque
# na seleção.
_BORDA_REPOUSO = 1.0
_BORDA_HOVER = 1.0
_BORDA_SELECAO = 2.0


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

        self._pen_chip = QPen(QColor("#FFFFFF"))  # texto do chip sobre o selo escuro — fixo
        self._icon_star = icons.pixmap("star-filled", "#FFFFFF", 12)
        self._icon_hidden = icons.pixmap("eye-off", "#FFFFFF", 12)
        self._icon_tags = icons.pixmap("nav-tags", "#FFFFFF", 12)

        self._cell = CELL  # tamanho devolvido por sizeHint(); ver set_icon_size
        self.refresh_theme()

    @staticmethod
    def _qcolor(rgba: tuple[int, int, int, float]) -> QColor:
        r, g, b, a = rgba
        c = QColor(r, g, b)
        c.setAlphaF(a)
        return c

    def refresh_theme(self) -> None:
        """Recalcula as cores em cache a partir de `theme.current_colors()`
        (Fatia 43) — chamado no `__init__` e de novo sempre que o modo
        claro/escuro trocar ao vivo. Continua tudo pré-computado FORA de
        `paint()`, só que agora pode ser refeito, não só computado uma vez."""
        pal = theme.current_colors()

        # A base é `surface`, não `bg` (corrigido na Fatia 47). O card mora
        # DENTRO do QFrame#card da grade, que é pintado com `$surface` — até a
        # Fatia 43 as duas cores eram o mesmo branco e a distinção não
        # aparecia, mas desde que o fundo virou um degrau mais fundo que o
        # painel, pintar o card com `bg` deixava cada célula um retângulo
        # escuro sobre o painel claro.
        # Desde a Fatia 50 o card não pinta fundo em repouso (perdeu a
        # moldura), então não há mais um `_brush_surface`. A base segue
        # importando: é sobre ELA que os véus de hover e seleção são
        # compostos, e compor sobre `bg` daria uma pastilha de tom errado.
        base = pal["surface"]
        self._pen_name = QPen(QColor(pal["text"]))
        self._brush_hover = QColor(theme.blend(pal["hover"], base))
        self._brush_selected = QColor(theme.blend(pal["selection"], base))
        self._pen_border = self._qcolor(pal["border"])
        # No hover o contorno passa a ser visível de verdade (era o mesmo
        # `border` quase transparente): num tema escuro, um véu de 6% de
        # branco no fundo praticamente não se vê, e o card não respondia ao
        # mouse. O contorno é o sinal barato e legível nos dois modos.
        self._pen_hover_border = QColor(pal["text_disabled"])
        self._pen_selected_border = QColor(pal["accent"])
        self._type_tint_color = QColor(pal["type_tint"])

        # O raio acompanha a variante ATIVA. Era constante de módulo, avaliada
        # no import a partir de `theme.DEFAULT` — trocar de variante ao vivo
        # (a vitrine faz isso) deixava o card com o raio da variante antiga.
        self._radius = theme.RADII[theme.current_variant().radius][1]

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

        # Card SEM moldura (Fatia 50). Em repouso não há fundo nem contorno:
        # quem separa um card do outro é o espaçamento, e a imagem manda —
        # era o que o mockup escolhido pelo Rafael fazia, e o retângulo com
        # fundo e borda em volta de cada miniatura competia com ela.
        #
        # Os estados migraram para a BORDA DA MINIATURA (ver `_paint_thumb`).
        # Aqui sobra só um véu de fundo em hover/seleção, que sozinho não
        # bastaria mas ajuda a mancha do card a acompanhar o cursor.
        if selected or hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._brush_selected if selected else self._brush_hover)
            painter.drawRoundedRect(QRectF(card_rect), self._radius, self._radius)

        # Miniatura sempre QUADRADA (pedido do Rafael: "sem achatar nada") —
        # o lado vem da LARGURA do card, que é o que cell_for_icon() garante
        # bater exatamente com o tamanho que o modelo escalou a imagem para.
        lado = card_rect.width() - 2 * CARD_PAD
        thumb_rect = QRect(card_rect.x() + CARD_PAD, card_rect.y() + CARD_PAD, lado, lado)
        self._paint_thumb(painter, index, thumb_rect, selected=selected, hover=hover)

        name_rect = QRect(
            card_rect.x() + CARD_PAD, thumb_rect.bottom() + CARD_GAP,
            card_rect.width() - 2 * CARD_PAD, NAME_HEIGHT,
        )
        self._paint_name(painter, index, name_rect)

        painter.restore()

    # ---- miolo ----

    def _paint_thumb(self, painter: QPainter, index, rect: QRect, *,
                     selected: bool = False, hover: bool = False) -> None:
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
            # Recorte arredondado de verdade (Fatia 60): antes a borda fina
            # era só um contorno desenhado POR CIMA da imagem, nunca uma
            # máscara — os cantos retos de uma imagem quadrada apareciam
            # vazando por baixo dela. `setClipPath` recorta o desenho da
            # miniatura no mesmo raio da borda, então os cantos somem de
            # verdade.
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), self._radius - 2, self._radius - 2)
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(x, y, pix)
            painter.restore()
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._type_tint_color)
            painter.drawRoundedRect(QRectF(rect), self._radius - 2, self._radius - 2)

        # A borda da MINIATURA é o que carrega os três estados desde a Fatia
        # 50, quando o card perdeu a moldura. Ela é desenhada por cima da
        # imagem, então precisa vir DEPOIS do drawPixmap.
        if selected:
            caneta = QPen(self._pen_selected_border, _BORDA_SELECAO)
        elif hover:
            caneta = QPen(self._pen_hover_border, _BORDA_HOVER)
        else:
            caneta = QPen(self._pen_border, _BORDA_REPOUSO)
        meia = _BORDA_SELECAO / 2
        painter.setPen(caneta)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(rect).adjusted(meia, meia, -meia, -meia),
            self._radius - 2, self._radius - 2,
        )

        if bool(index.data(HIDDEN_ROLE)):
            self._badge(painter, rect.x() + 4, rect.y() + 4, self._icon_hidden)
        if bool(index.data(STARRED_ROLE)):
            self._badge(painter, rect.right() - _BADGE - 4, rect.y() + 4, self._icon_star)
        # Canto inferior-direito (Fatia 61) — o único que ainda estava livre:
        # oculto = superior-esquerdo, favorito = superior-direito, extensão =
        # inferior-esquerdo (`_chip`, mais abaixo). Fica fora do `_chip` de
        # extensão de propósito: são informações diferentes, não competem
        # pelo mesmo canto.
        if bool(index.data(HAS_TAGS_ROLE)):
            self._badge(painter, rect.right() - _BADGE - 4, rect.bottom() - _BADGE - 4,
                        self._icon_tags)

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
        """Nome em 1 linha, alinhado à ESQUERDA, com reticências no final
        quando não cabe (Fatia 59). Antes era centralizado com quebra em até
        2 linhas: um nome comprido cortava tanto o começo quanto o fim sem
        aviso nenhum de que havia mais texto. Alinhado à esquerda pelo menos
        mostra o início do nome, e a elisão deixa claro que foi cortado.
        Continua verticalmente centrado no espaço reservado (mesmo motivo de
        antes: nome curto não pode ficar colado no topo)."""
        nome = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.setFont(self._font_name)
        painter.setPen(self._pen_name)
        elidido = self._fm_name.elidedText(nome, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elidido
        )
