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

from PySide6.QtCore import QElapsedTimer, QRect, QRectF, QSize, Qt, QTimer
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
    TYPE_ROLE,
    cell_for_icon,
)

_BADGE = 20              # lado do selo (estrela / oculto)
_BADGE_BG = QColor(0, 0, 0, 140)   # fundo dos selos sobre a miniatura

# Espessura do contorno de SELEÇÃO (Fatia 47) — o único estado que ainda usa
# contorno. Repouso e hover pararam de ter contorno na Fatia 74: quem separa
# o card do fundo em hover é o FUNDO próprio do card (`theme.SURFACE_RAISED`),
# que aparece só sob o cursor, crescendo de leve.
_BORDA_SELECAO = 2.0

# O quanto a pastilha de fundo CRESCE em hover, em px por lado (Fatia 74).
#
# Isto era uma ELEVAÇÃO (o card inteiro subia 2px) e virou crescimento por um
# motivo concreto, relatado pelo Rafael: "a animação parece meio travada".
# Subir o card exigia deslocar `card_rect`, que é um `QRect` INTEIRO — 2px de
# curso davam só 3 posições possíveis (0, -1, -2), ou seja, a animação toda
# acontecia em 3 saltos visíveis, e a miniatura era redesenhada em Y diferente
# a cada salto. Crescer a pastilha usa `QRectF` (float) com antialiasing: o
# movimento é subpixel e contínuo, e a miniatura fica parada — nada "pula".
_CRESCIMENTO_HOVER = 2.0

# Duração da transição de hover, em ms (ajuste da Fatia 74: "a animação
# poderia ser um pouco mais suave" — antes o card saltava direto de repouso
# pra hover num frame só). ~60fps por `_hover_timer.setInterval`.
_HOVER_ANIM_MS = 180


def _suavizar(t: float) -> float:
    """Curva de aceleração "ease-out" cúbica (Fatia 74, 2º ajuste).

    A 1ª versão da animação era LINEAR: começava e parava de repente, na
    mesma velocidade do início ao fim — é isso que o olho lê como
    "travado"/mecânico, mesmo quando nenhum quadro foi perdido. Ease-out
    arranca rápido e desacelera no fim, que é como as coisas se movem no
    mundo real (e o padrão de qualquer UI moderna).

    O progresso GUARDADO continua linear; a curva é aplicada só na hora de
    pintar — aplicá-la a cada passo comporia a curva sobre ela mesma.
    """
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _lerp_color(c0: QColor, c1: QColor, t: float) -> QColor:
    """Interpola duas cores por `t` (0..1) — é o que faz o fundo do card
    NASCER aos poucos a partir da cor do painel, em vez de aparecer pronto
    num frame só (Fatia 74)."""
    if t <= 0.0:
        return c0
    if t >= 1.0:
        return c1
    return QColor(
        round(c0.red() + (c1.red() - c0.red()) * t),
        round(c0.green() + (c1.green() - c0.green()) * t),
        round(c0.blue() + (c1.blue() - c0.blue()) * t),
    )


class AssetCardDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._font_name = QFont()
        self._font_name.setPixelSize(12)  # px, não pt: mais previsível entre telas
        self._fm_name = QFontMetrics(self._font_name)

        self._font_type = QFont()
        self._font_type.setPixelSize(10)
        self._fm_type = QFontMetrics(self._font_type)

        self._font_chip = QFont()
        self._font_chip.setPixelSize(10)
        self._font_chip.setBold(True)
        self._fm_chip = QFontMetrics(self._font_chip)

        self._pen_chip = QPen(QColor("#FFFFFF"))  # texto do chip sobre o selo escuro — fixo
        self._icon_star = icons.pixmap("star-filled", "#FFFFFF", 12)
        self._icon_hidden = icons.pixmap("eye-off", "#FFFFFF", 12)
        self._icon_tags = icons.pixmap("nav-tags", "#FFFFFF", 12)

        self._cell = CELL  # tamanho devolvido por sizeHint(); ver set_icon_size
        # Índice sob o botão do mouse pressionado (Fatia 74) — estado de
        # INTERAÇÃO, não de tema, por isso mora aqui e não em `refresh_theme`.
        # `AssetGridView` chama `set_pressed()` no mousePress/Release.
        self._pressed_index = None

        # Progresso animado do hover, por LINHA (Fatia 74, ajuste: "a
        # animação poderia ser um pouco mais suave"). 0 = repouso, 1 = mouse
        # em cima; `AssetGridView.mouseMoveEvent` chama `set_hover()` quando
        # o card sob o cursor muda, e um QTimer compartilhado interpola o
        # valor até o alvo em vez de saltar direto — é isto que `paint()` lê
        # pra desenhar a sombra crescendo/o card subindo aos poucos.
        self._hover_progress: dict[int, float] = {}
        self._hover_target: dict[int, float] = {}
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(16)  # ~60fps
        self._hover_timer.timeout.connect(self._tick_hover)
        self._hover_clock = QElapsedTimer()

        self.refresh_theme()

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
        self._pen_type = QPen(QColor(pal["text_muted"]))
        self._brush_selected = QColor(theme.blend(pal["selection"], base))
        self._pen_selected_border = QColor(pal["accent"])
        self._type_tint_color = QColor(pal["type_tint"])

        # Fundo do card por estado (Fatia 74) — ver `theme.SURFACE_RAISED` pro
        # porquê disto ter substituído a sombra pintada à mão. `_brush_base`
        # é a cor do PAINEL: pintar ela é o mesmo que não pintar nada, e é o
        # ponto de partida da animação (o fundo de hover nasce dela).
        self._brush_base = QColor(base)
        self._brush_card_hover = QColor(pal["surface_raised"])
        self._brush_card_press = QColor(pal["surface_sunken"])
        # Mesmos três, já com o véu de seleção composto por cima — assim um
        # card selecionado também responde ao mouse, sem precisar compor cor
        # (operação de string) dentro do `paint()`.
        self._brush_selected_hover = QColor(
            theme.blend(pal["selection"], pal["surface_raised"]))
        self._brush_selected_press = QColor(
            theme.blend(pal["selection"], pal["surface_sunken"]))

        # O raio acompanha a variante ATIVA. Era constante de módulo, avaliada
        # no import a partir de `theme.DEFAULT` — trocar de variante ao vivo
        # (a vitrine faz isso) deixava o card com o raio da variante antiga.
        self._radius = theme.RADII[theme.current_variant().radius][1]

        # Selos (estrela/oculto/tags) e o chip de extensão acompanham o raio
        # do card (Fatia 74, ajuste pedido pelo Rafael: "as bordas das tags
        # deveriam acompanhar de acordo com a borda atual do grid do
        # asset") — antes eram valores fixos (6 e 4) escolhidos quando o
        # raio "marcante" era 12; ficaram pequenos demais depois dele virar
        # 16 na Fatia 73 e iam continuar errados em qualquer raio futuro.
        radius_thumb = self._radius - 2  # mesmo raio que _paint_thumb usa
        self._radius_badge = max(4.0, radius_thumb * 0.5)
        self._radius_chip = max(3.0, radius_thumb * 0.35)

    def set_icon_size(self, px: int) -> None:
        """Chamado pela AssetGridView quando o slider de tamanho muda."""
        px = max(MIN_ICON, min(MAX_ICON, px))
        self._cell = cell_for_icon(px)

    def set_pressed(self, index) -> None:
        """`AssetGridView` chama no mousePress/Release (Fatia 74) — não dá
        pra confiar em `QStyle.State_Sunken` vir preenchido sozinho pra um
        `QListView` customizado, então o estado de "botão pressionado" é
        rastreado à mão, igual ao hover já era antes (`setMouseTracking`)."""
        self._pressed_index = index if (index is not None and index.isValid()) else None

    def set_hover(self, old_index, new_index) -> None:
        """`AssetGridView.mouseMoveEvent`/`leaveEvent` chamam quando o card
        sob o cursor muda (Fatia 74) — dispara a animação de entrada do novo
        índice e de saída do antigo, em vez de o `paint()` ler um booleano e
        saltar direto pro estado final."""
        if old_index is not None and old_index.isValid():
            self._hover_target[old_index.row()] = 0.0
            self._hover_progress.setdefault(old_index.row(), 1.0)
        if new_index is not None and new_index.isValid():
            self._hover_target[new_index.row()] = 1.0
            self._hover_progress.setdefault(new_index.row(), 0.0)
        if self._hover_target and not self._hover_timer.isActive():
            self._hover_clock.start()
            self._hover_timer.start()

    def clear_hover(self) -> None:
        """Zera a animação de hover (Fatia 74). O progresso é indexado por
        LINHA, e linha não é identidade estável: depois de trocar um filtro
        ou recarregar a grade, a linha 7 é outro asset. Sem zerar, um card
        que nunca viu o mouse aparecia aceso. `AssetGridView` chama isto
        quando o modelo é resetado."""
        self._hover_progress.clear()
        self._hover_target.clear()
        self._hover_timer.stop()

    def _tick_hover(self) -> None:
        """Um passo da animação de hover — avança cada linha em direção ao
        seu alvo proporcionalmente ao tempo real decorrido (não a um número
        fixo de frames, pra não variar de velocidade com a carga da tela)."""
        decorrido_ms = self._hover_clock.restart()
        passo = decorrido_ms / _HOVER_ANIM_MS if _HOVER_ANIM_MS else 1.0
        ainda_anima = False
        tocadas = list(self._hover_target)
        for row in tocadas:
            alvo = self._hover_target[row]
            atual = self._hover_progress.get(row, 0.0)
            if atual < alvo:
                atual = min(alvo, atual + passo)
            elif atual > alvo:
                atual = max(alvo, atual - passo)
            if atual == alvo:
                del self._hover_target[row]
                if alvo <= 0.0:
                    self._hover_progress.pop(row, None)
                else:
                    self._hover_progress[row] = atual
            else:
                self._hover_progress[row] = atual
                ainda_anima = True

        if not ainda_anima:
            self._hover_timer.stop()

        # Repinta SÓ as células que estão animando, não o viewport inteiro
        # (Fatia 74, 2º ajuste). `viewport().update()` a cada 16ms mandava o
        # Qt redesenhar todos os cards visíveis — cada um com sua miniatura —
        # 60 vezes por segundo, por causa de uma pastilha que mudou de tom em
        # UMA célula. Era a outra metade do "travado": não é que a curva
        # estivesse errada, é que alguns quadros não davam conta.
        view = self.parent()
        model = view.model() if view is not None else None
        if view is None or model is None:
            return
        for row in tocadas:
            if 0 <= row < model.rowCount():
                # A pastilha cresce pra fora do retângulo do item; a margem
                # extra garante que a borda antiga também seja apagada.
                view.viewport().update(
                    view.visualRect(model.index(row)).adjusted(-4, -4, 4, 4)
                )

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
        pressed = self._pressed_index is not None and self._pressed_index == index

        # Estado do card (Fatia 74, revisão visual pedida pelo Rafael):
        # repouso PLANO de verdade (não pinta fundo nenhum), hover mostra a
        # pastilha de fundo crescendo de leve, clique "afunda" (tom mais
        # fundo, pastilha no tamanho normal). Tudo DENTRO do retângulo do
        # card — ver `theme.SURFACE_RAISED` pro porquê da sombra pintada à mão
        # ter sido removida (era recortada pela célula e escurecia o card).
        #
        # O quanto hover está "ligado" vem do progresso ANIMADO
        # (`_hover_progress`, 0..1), não de um salto binário — é isto que dá
        # a sensação de transição suave em vez de aparecer pronto num frame
        # só. Quando não há animação em andamento pra esta linha (ex.: os
        # testes de paint(), que nunca chamam `set_hover`), cai de volta pro
        # estado nativo do Qt (`hover`), 0 ou 1 direto — sem isso o card só
        # reagiria depois do primeiro `mouseMoveEvent` de verdade.
        progresso_hover = self._hover_progress.get(index.row())
        if progresso_hover is None:
            progresso_hover = 1.0 if hover else 0.0
        # O valor guardado é linear; a curva entra só aqui (ver `_suavizar`).
        suave = _suavizar(progresso_hover)

        if pressed:
            fundo = self._brush_selected_press if selected else self._brush_card_press
        elif selected:
            fundo = _lerp_color(self._brush_selected, self._brush_selected_hover, suave)
        else:
            fundo = _lerp_color(self._brush_base, self._brush_card_hover, suave)

        # Em repouso e sem seleção o fundo é IGUAL ao do painel — pintar
        # seria desenhar o invisível em cada célula, a cada frame.
        if selected or pressed or progresso_hover > 0.0:
            # `QRectF` (float) de propósito: o crescimento é subpixel e sai
            # antialiasado, então a pastilha "respira" de forma contínua. Com
            # `QRect` inteiro seriam 3 saltos visíveis — era exatamente o que
            # deixava a animação "travada".
            cresce = 0.0 if pressed else _CRESCIMENTO_HOVER * suave
            alvo = QRectF(card_rect).adjusted(-cresce, -cresce, cresce, cresce)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fundo)
            painter.drawRoundedRect(alvo, self._radius + cresce, self._radius + cresce)

        # Miniatura sempre QUADRADA (pedido do Rafael: "sem achatar nada") —
        # o lado vem da LARGURA do card, que é o que cell_for_icon() garante
        # bater exatamente com o tamanho que o modelo escalou a imagem para.
        lado = card_rect.width() - 2 * CARD_PAD
        thumb_rect = QRect(card_rect.x() + CARD_PAD, card_rect.y() + CARD_PAD, lado, lado)
        self._paint_thumb(painter, index, thumb_rect, selected=selected)

        name_rect = QRect(
            card_rect.x() + CARD_PAD, thumb_rect.bottom() + CARD_GAP,
            card_rect.width() - 2 * CARD_PAD, NAME_HEIGHT,
        )
        self._paint_name(painter, index, name_rect)

        painter.restore()

    # ---- miolo ----

    def _paint_thumb(self, painter: QPainter, index, rect: QRect, *,
                     selected: bool = False) -> None:
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

        # A borda da MINIATURA agora só aparece pra SELEÇÃO (Fatia 74) — o
        # contorno de repouso/hover morreu junto com a borda dura do card
        # inteiro; hover é a sombra crescendo (`paint()`), não um contorno
        # mudando de cor. Continua desenhada DEPOIS do drawPixmap, por cima
        # da imagem.
        if selected:
            meia = _BORDA_SELECAO / 2
            painter.setPen(QPen(self._pen_selected_border, _BORDA_SELECAO))
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
        painter.drawRoundedRect(QRectF(x, y, _BADGE, _BADGE), self._radius_badge, self._radius_badge)
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
        painter.drawRoundedRect(rect, self._radius_chip, self._radius_chip)

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
        linha_nome = QRect(rect.x(), rect.y(), rect.width(), 19)
        elidido = self._fm_name.elidedText(
            nome, Qt.TextElideMode.ElideRight, linha_nome.width())
        painter.drawText(
            linha_nome, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elidido
        )

        tipo = _asset_type_label(index.data(TYPE_ROLE))
        if tipo:
            linha_tipo = QRect(rect.x(), rect.y() + 18, rect.width(), 15)
            painter.setFont(self._font_type)
            painter.setPen(self._pen_type)
            elidido_tipo = self._fm_type.elidedText(
                tipo, Qt.TextElideMode.ElideRight, linha_tipo.width())
            painter.drawText(
                linha_tipo,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elidido_tipo,
            )


def _asset_type_label(asset_type: str | None) -> str:
    """Rótulo humano do tipo do asset, usado como subtítulo do card."""
    return {
        "model": "Modelo 3D",
        "scene": "Cena 3D",
        "pbr_set": "Material PBR",
        "other": "Outro material",
        "texture": "Textura",
        "cutout": "Recorte",
        "hdri": "HDRI",
        "vector": "Vetor",
        "reference": "Referência",
        "psd": "Photoshop",
        "ies": "Perfil IES",
        "lut": "LUT",
    }.get(asset_type or "", "")
