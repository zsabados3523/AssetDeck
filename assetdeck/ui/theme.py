"""Tema visual do AssetDeck: tokens, paleta e folha de estilo (QSS).

Fonte da verdade de TODA cor, raio, espaçamento e fonte da interface.

Regra do projeto: **nenhum `setStyleSheet` fora deste módulo.** Cor nova entra
aqui como token e vira `$nome` no `theme.qss` — assim o Rafael consegue mudar a
identidade visual inteira num lugar só.

Fatos do Qt que moldaram este módulo (verificados na máquina, não presumidos):

* A `QPalette` padrão vem do tema do Zorin quando o app roda no X11, mas do
  Fusion quando roda headless. Sem `app.setPalette(build_palette())` o app fica
  diferente em cada máquina e o teste headless não vale para a tela real.
* `background-color: rgba(...)` compõe de verdade sobre o pai já pintado. Blur
  real não existe aqui de qualquer jeito: `QGraphicsBlurEffect` borra o
  conteúdo do próprio widget (as miniaturas!), e o Mutter (compositor do Zorin)
  não implementa blur atrás da janela. O visual não depende disso — segue a
  referência do Craft: cartão branco sobre cinza claro, separado por sombra.
* `url()` no QSS exige caminho ABSOLUTO. Caminho com espaço funciona — o que
  importa, porque o projeto mora em "/00 - PROJETOS/".
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template

from assetdeck import config

log = logging.getLogger(__name__)

QSS_FILE = Path(__file__).parent / "theme.qss"

# --------------------------------------------------------------------------
# Paleta base
# --------------------------------------------------------------------------
# Escolhas do Rafael (F4): tema claro lavanda, destaque azul-petróleo, fundo
# liso. A primeira tentativa usou fundo lavanda e ele reprovou na tela: ficou
# pesado. Direção corrigida, olhando a referência do Craft de novo — o fundo lá
# NÃO tem cor: é cinza bem claro, e o que dá a sensação de acabamento é o
# cartão BRANCO flutuando sobre ele, com sombra suave e nenhum contorno duro.
# A cor aparece só em detalhe pequeno (seleção, foco, um botão principal).

BG = "#FFFFFF"          # fundo da janela: branco puro
BG_TINT = "#F0F0F2"     # variação do fundo (trilho de barra de rolagem, cabeçalho)

# Monocromático: o "destaque" não é mais uma cor, é um cinza bem escuro. Serve
# ao botão principal e à ênfase de texto. Cor de verdade sobrou só em dois
# lugares onde ela CARREGA informação: a cor da tag e o tipo do asset.
ACCENT = "#4A4A52"
ACCENT_HOVER = "#5A5A63"
ACCENT_PRESS = "#38383F"
ON_ACCENT = "#FFFFFF"

TITLE = "#111216"       # títulos: mais escuros que o corpo, é o que dá hierarquia
TEXT = "#1F2024"
TEXT_MUTED = "#6B6C74"
TEXT_DISABLED = "#A9AAB2"

WARNING = "#8A5A12"     # substitui o "#b07d2b" que estava inline no details_panel
DANGER = "#A32D2D"

POPOVER = "#FFFFFF"     # menus e popups são JANELAS separadas: sempre opacos
BORDER = (0, 0, 0, 0.09)         # contorno de campo/botão
BORDER_STRONG = (0, 0, 0, 0.28)  # contorno de controle (caixa de checkbox)
FOCUS = "#8A8B93"                # foco monocromático: contorno mais escuro

# Seleção monocromática: pastilha de cinza claro com o texto normal por cima.
SELECTION = (0, 0, 0, 0.065)
HOVER = (0, 0, 0, 0.035)

# Fundo do card quando o asset não tem miniatura. Decisão do Rafael: nada de
# cor por tipo — uma pastilha cinza só, igual ao ACCENT dos botões, e o
# reconhecimento do tipo passa a vir do rótulo de extensão no canto do card
# (".fbx"/".exr"/...), não mais de cor. Consumido pelo delegate (Fatia 27).
TYPE_TINT = ACCENT
ON_TYPE_TINT = "#FFFFFF"  # texto/glifo sobre a pastilha acima

# Variações que o Rafael escolhe na tela (vitrine da Fatia 24).
# Fundo e painel são os DOIS brancos: o que separa um do outro é uma linha de
# contorno quase invisível mais uma sombra de opacidade baixa. Este número é a
# opacidade dessa linha — é o único ajuste de "quanto o painel se destaca".
SEPARATION = {"sutil": 0.05, "media": 0.075, "forte": 0.11}
RADII = {  # (painel, card, controle)
    "discreto": (10, 8, 6),
    "marcante": (16, 12, 9),
}
FONTS = {
    "inter": "Inter",
    "sistema": "",  # vazio = mantém a fonte padrão do sistema
}

BACKGROUNDS = ("liso", "grao")


@dataclass(frozen=True)
class Variant:
    """Uma combinação de escolhas visuais.

    O padrão é o que o Rafael pediu: fundo liso, translucidez média, cantos
    discretos, fonte Inter. A vitrine (`theme_gallery.py`) troca estes campos ao
    vivo para ele comparar as alternativas na tela antes de bater o martelo.
    """

    background: str = "liso"      # liso | grao
    separation: str = "media"     # sutil | media | forte (opacidade da linha)
    radius: str = "discreto"      # discreto | marcante
    font: str = "inter"           # inter | sistema

    def __post_init__(self) -> None:
        for campo, valor, validos in (
            ("background", self.background, BACKGROUNDS),
            ("separation", self.separation, tuple(SEPARATION)),
            ("radius", self.radius, tuple(RADII)),
            ("font", self.font, tuple(FONTS)),
        ):
            if valor not in validos:
                raise ValueError(
                    f"Variant.{campo}={valor!r} é inválido; use um de {validos}."
                )


DEFAULT = Variant()


# --------------------------------------------------------------------------
# Cor: conversão, mistura e contraste (WCAG)
# --------------------------------------------------------------------------

def hex_to_rgb(cor: str) -> tuple[int, int, int]:
    """"#RRGGBB" -> (r, g, b)."""
    s = cor.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Cor hex inválida: {cor!r} (esperado '#RRGGBB').")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0, min(255, c))):02X}" for c in rgb)


def rgba_css(rgba: tuple[int, int, int, float]) -> str:
    """(r, g, b, alfa) -> "rgba(r, g, b, alfa)" para o QSS."""
    r, g, b, a = rgba
    return f"rgba({r}, {g}, {b}, {a})"


def blend(topo: tuple[int, int, int, float], fundo: str) -> str:
    """Cor resultante de pintar `topo` (com alfa) sobre `fundo` (hex opaco).

    O Qt compõe assim de verdade — conferido comparando pixels. É com esta
    função que o teste de contraste mede o texto sobre um painel TRANSLÚCIDO,
    em vez de fingir que o painel é branco puro.
    """
    r, g, b, a = topo
    fr, fg, fb = hex_to_rgb(fundo)
    return rgb_to_hex((
        r * a + fr * (1 - a),
        g * a + fg * (1 - a),
        b * a + fb * (1 - a),
    ))


def _canal_linear(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(cor: str) -> float:
    """Luminância relativa da WCAG 2.1 (0 = preto, 1 = branco)."""
    r, g, b = hex_to_rgb(cor)
    return (0.2126 * _canal_linear(r)
            + 0.7152 * _canal_linear(g)
            + 0.0722 * _canal_linear(b))


def contrast_ratio(frente: str, fundo: str) -> float:
    """Razão de contraste da WCAG entre duas cores opacas (1.0 a 21.0).

    Legibilidade foi pedido EXPLÍCITO do Rafael, então isto não é enfeite:
    `tests/test_theme.py` falha se algum par texto/superfície ficar abaixo do
    mínimo. Referência: 4.5 para texto normal, 3.0 para texto secundário.
    """
    a, b = relative_luminance(frente), relative_luminance(fundo)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)


# --------------------------------------------------------------------------
# Fundo com grão (variante "grao")
# --------------------------------------------------------------------------

TILE = 256      # lado do ladrilho, em pixels
GRAIN_SIGMA = 2.6   # desvio-padrão do ruído; acima de ~4 já vira sujeira visível
GRAIN_SEED = 20260801


def background_tile_path(variant: Variant = DEFAULT) -> Path | None:
    """Caminho do ladrilho de grão, gerando-o se preciso. `None` no fundo liso.

    Não é gradiente (o Rafael vetou gradiente): é ruído gaussiano fino sobre a
    cor de fundo, o "grão de papel". Gerar custa ~20 ms UMA vez; o arquivo fica
    em cache com o hash dos parâmetros no nome, então mudar a cor de fundo gera
    um ladrilho novo em vez de servir o velho.
    """
    if variant.background != "grao":
        return None

    assinatura = f"{BG}-{TILE}-{GRAIN_SIGMA}-{GRAIN_SEED}"
    nome = f"bg-{hashlib.sha1(assinatura.encode()).hexdigest()[:12]}.png"
    destino = config.cache_dir() / "theme" / nome
    if destino.exists():
        return destino

    import numpy as np
    from PySide6.QtGui import QImage

    destino.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(GRAIN_SEED)
    base = np.array(hex_to_rgb(BG), dtype=np.float32)
    ruido = rng.normal(0.0, GRAIN_SIGMA, size=(TILE, TILE, 1)).astype(np.float32)
    pixels = np.clip(base + ruido, 0, 255).astype(np.uint8)

    # RGBA8888 contíguo: o QImage aponta para o buffer, então `copy()` é
    # obrigatório antes de o array sair de escopo.
    rgba = np.dstack([pixels, np.full((TILE, TILE, 1), 255, dtype=np.uint8)])
    rgba = np.ascontiguousarray(rgba)
    img = QImage(rgba.data, TILE, TILE, 4 * TILE, QImage.Format.Format_RGBA8888).copy()

    if not img.save(str(destino), "PNG"):
        raise RuntimeError(f"Não consegui gravar o ladrilho de fundo em {destino}")
    log.info("Ladrilho de fundo do tema gerado em %s", destino)
    return destino


def icon_asset_path(nome: str, cor: str, tam: int = 12) -> Path:
    """Ícone de `ui/icons.py` cacheado como PNG em disco.

    QSS só aceita `url()` apontando para um ARQUIVO — não dá para passar um
    QPixmap gerado em memória. Mesmo padrão do ladrilho de fundo: o nome do
    arquivo carrega o hash dos parâmetros, então mudar a cor gera um PNG novo
    em vez de servir o velho.
    """
    from assetdeck.ui import icons as icons_mod

    assinatura = f"{nome}-{cor}-{tam}"
    nome_arquivo = f"icon-{hashlib.sha1(assinatura.encode()).hexdigest()[:12]}.png"
    destino = config.cache_dir() / "theme" / nome_arquivo
    if destino.exists():
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    pix = icons_mod.pixmap(nome, cor=cor, tam=tam)
    if not pix.save(str(destino), "PNG"):
        raise RuntimeError(f"Não consegui gravar o ícone '{nome}' em {destino}")
    return destino


# --------------------------------------------------------------------------
# Tokens e QSS
# --------------------------------------------------------------------------

def separation_alpha(variant: Variant = DEFAULT) -> float:
    """Opacidade da linha que separa o painel do fundo (ambos brancos)."""
    return SEPARATION[variant.separation]


def surface_solid(variant: Variant = DEFAULT) -> str:
    """Cor do painel. Branco — igual ao fundo, por decisão do Rafael.

    Continua existindo como função porque é contra esta cor que o contraste do
    texto é medido, e porque o dia em que o painel deixar de ser branco puro é
    aqui que muda.
    """
    return BG


def build_tokens(variant: Variant = DEFAULT) -> dict[str, str]:
    """Todos os `$nome` que o theme.qss pode usar."""
    raio_painel, raio_card, raio_controle = RADII[variant.radius]
    familia = FONTS[variant.font]

    ladrilho = background_tile_path(variant)
    bg_image = ""
    if ladrilho is not None:
        # Caminho ABSOLUTO — url() relativo resolve contra o cwd e falha calado.
        bg_image = f"background-image: url({ladrilho});\n    background-repeat: repeat;"

    return {
        "bg": BG,
        "bg_tint": BG_TINT,
        "bg_image": bg_image,

        "surface": BG,
        "surface_hover": rgba_css(HOVER),
        "selection": rgba_css(SELECTION),
        "field": BG,
        "popover": POPOVER,

        "border": rgba_css(BORDER),
        "border_strong": rgba_css(BORDER_STRONG),
        "hairline": rgba_css((0, 0, 0, separation_alpha(variant))),
        "focus": FOCUS,

        "accent": ACCENT,
        "accent_hover": ACCENT_HOVER,
        "accent_press": ACCENT_PRESS,
        "on_accent": ON_ACCENT,

        "title": TITLE,
        "text": TEXT,
        "text_muted": TEXT_MUTED,
        "text_disabled": TEXT_DISABLED,
        "warning": WARNING,
        "danger": DANGER,

        "radius_panel": f"{raio_painel}px",
        "radius_card": f"{raio_card}px",
        "radius_control": f"{raio_controle}px",

        "pad_s": "4px",
        "pad_m": "8px",
        "pad_l": "12px",

        "font_family": f'"{familia}"' if familia else "inherit",
        "font_size": "13px",
        "font_size_small": "12px",
        "font_size_title": "15px",

        "check_icon": str(icon_asset_path("check", ON_ACCENT, 12)),
        "chevron_icon": str(icon_asset_path("chevron-down", TEXT_MUTED, 12)),
    }


def build_qss(variant: Variant = DEFAULT) -> str:
    """Lê o theme.qss e substitui os tokens.

    Usa `Template.substitute` (não `safe_substitute`) de propósito: token
    esquecido levanta `KeyError` na hora, em vez de vazar um "$nome" para
    dentro do QSS, onde o Qt descartaria a regra em silêncio.
    """
    if not QSS_FILE.exists():
        raise FileNotFoundError(f"Folha de estilo do tema não encontrada: {QSS_FILE}")
    return Template(QSS_FILE.read_text(encoding="utf-8")).substitute(build_tokens(variant))


def build_palette(variant: Variant = DEFAULT):
    """Paleta do app.

    Obrigatória: sem ela o Qt herda a paleta do tema do Zorin no X11, e aí o
    app muda de cara conforme a máquina — e o teste headless deixa de valer
    para a tela real. Cobre também o que o QSS alcança mal (texto de item view,
    seleção, tooltip).
    """
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    superficie = QColor(surface_solid(variant))
    C = QColor

    p.setColor(QPalette.ColorRole.Window, C(BG))
    p.setColor(QPalette.ColorRole.WindowText, C(TEXT))
    p.setColor(QPalette.ColorRole.Base, superficie)
    p.setColor(QPalette.ColorRole.AlternateBase, C(BG_TINT))
    p.setColor(QPalette.ColorRole.Text, C(TEXT))
    p.setColor(QPalette.ColorRole.PlaceholderText, C(TEXT_DISABLED))
    p.setColor(QPalette.ColorRole.Button, superficie)
    p.setColor(QPalette.ColorRole.ButtonText, C(TEXT))
    p.setColor(QPalette.ColorRole.BrightText, C(DANGER))
    p.setColor(QPalette.ColorRole.Highlight, C(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, C(ON_ACCENT))
    p.setColor(QPalette.ColorRole.ToolTipBase, C(POPOVER))
    p.setColor(QPalette.ColorRole.ToolTipText, C(TEXT))
    p.setColor(QPalette.ColorRole.Link, C(ACCENT))

    for grupo in (QPalette.ColorGroup.Disabled,):
        p.setColor(grupo, QPalette.ColorRole.Text, C(TEXT_DISABLED))
        p.setColor(grupo, QPalette.ColorRole.WindowText, C(TEXT_DISABLED))
        p.setColor(grupo, QPalette.ColorRole.ButtonText, C(TEXT_DISABLED))
    return p


def apply_card_shadow(widget) -> None:
    """Sombra suave para o painel "flutuar" sobre o fundo.

    Custo medido: repaint ~2,3x mais caro. Por isso vale em painel estático,
    mas NUNCA no container da grade — ela rola com centenas de itens e o efeito
    força o Qt a renderizar a subárvore inteira fora da tela a cada quadro.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    efeito = QGraphicsDropShadowEffect(widget)
    efeito.setBlurRadius(18)
    efeito.setXOffset(0)
    efeito.setYOffset(2)
    efeito.setColor(QColor(0, 0, 0, 28))  # cinza neutro e discreto, sem cor
    widget.setGraphicsEffect(efeito)


def make_card(inner, *, titulo: str | None = None, sombra: bool = True):
    """Envolve um widget num cartão branco de cantos arredondados.

    Este embrulho não é enfeite, é obrigatório para views: o viewport de um
    `QTreeWidget`/`QListView` pinta um retângulo no canto e vaza por cima de
    qualquer `border-radius` posto nela diretamente (`setFrameShape(NoFrame)`
    não resolve). O card arredondado por fora, com a view transparente por
    dentro, é o único arranjo em que o canto mostra o fundo de verdade.
    """
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)

    if titulo:
        rotulo = QLabel(titulo.upper())
        rotulo.setObjectName("sectionTitle")
        layout.addWidget(rotulo)

    layout.addWidget(inner)
    if sombra:
        apply_card_shadow(card)
    return card


def apply_theme(app, variant: Variant = DEFAULT) -> None:
    """Aplica estilo, paleta, fonte e QSS na aplicação inteira."""
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QStyleFactory

    estilo = QStyleFactory.create("Fusion")
    if estilo is None:  # nunca deve acontecer: Fusion é embutido no Qt
        log.error("Estilo Fusion indisponível; seguindo com o estilo padrão do sistema.")
    else:
        app.setStyle(estilo)

    familia = FONTS[variant.font]
    if familia:
        if familia in QFontDatabase.families():
            fonte = QFont(familia)
            fonte.setPointSize(10)
            app.setFont(fonte)
        else:
            log.warning(
                "Fonte %r não está instalada; usando a fonte padrão do sistema.", familia
            )

    app.setPalette(build_palette(variant))
    app.setStyleSheet(build_qss(variant))
    install_popup_corner_mask(app, variant)
    log.info(
        "Tema aplicado (fundo=%s, separação=%s, cantos=%s, fonte=%s).",
        variant.background, variant.separation, variant.radius, variant.font,
    )


class _PopupCornerMask:
    """Recorta QMenu/QDialog num retângulo arredondado de verdade.

    `WA_TranslucentBackground` foi testado e DESCARTADO: com ele ativo, o
    `background-color` do QSS simplesmente parou de ser pintado (sonda
    mostrou o meio da janela como `#00000000`) — o mesmo risco de depender
    do compositor que a Fatia 24 já tinha evitado pra janela principal, só
    que agora se confirmou na prática. `setMask()` com um `QRegion`
    arredondado não depende de compositor (usa a X-Shape extension) e,
    testado, manteve o fundo do QSS pintado normalmente.

    Não mexe em `QFileDialog`/`QColorDialog` — são diálogos nativos
    complexos, arredondar a janela deles é mais risco que ganho.
    """

    def __init__(self, radius_dialog: int, radius_menu: int) -> None:
        self._radius_dialog = radius_dialog
        self._radius_menu = radius_menu

    def __call__(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QColorDialog, QDialog, QFileDialog, QMenu

        if event.type() not in (QEvent.Type.Show, QEvent.Type.Resize):
            return False
        if isinstance(obj, (QFileDialog, QColorDialog)):
            return False
        if isinstance(obj, QMenu):
            self._mask(obj, self._radius_menu)
        elif isinstance(obj, QDialog):
            self._mask(obj, self._radius_dialog)
        return False

    @staticmethod
    def _mask(widget, radius: int) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath, QRegion

        if widget.width() <= 0 or widget.height() <= 0:
            return
        # Defesa extra: `setMask()` pode disparar outro Resize de volta pro
        # widget (o gerenciador de janelas confirma a mudança de geometria).
        # Sem este corte, isso reentraria no filtro e recalcularia a máscara
        # de novo pro MESMO tamanho, sem necessidade.
        tamanho = widget.size()
        if widget.property("_assetdeck_masked_size") == tamanho:
            return
        widget.setProperty("_assetdeck_masked_size", tamanho)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, widget.width(), widget.height()), radius, radius)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


_popup_filter_ref = None  # installEventFilter não segura referência sozinho


def install_popup_corner_mask(app, variant: Variant = DEFAULT) -> None:
    """Instala (ou REINSTALA, se o tema for reaplicado) o recorte de cantos
    de QMenu/QDialog. Ver `_PopupCornerMask` para o porquê de `setMask()`
    em vez de `WA_TranslucentBackground`.

    Bug pego rodando a suíte inteira: `apply_theme()` é chamado várias vezes
    em sequência em teste (`test_todas_as_variantes_aplicam_sem_erro` chama
    24x seguidas). Sem remover o filtro ANTERIOR antes de instalar o novo,
    eles se acumulavam no `QApplication` — que dura a sessão inteira de
    testes — e cada Show/Resize passava a ser reprocessado por dezenas de
    filtros ao mesmo tempo, travando a suíte por minutos. Por isso remove o
    filtro velho primeiro: nunca mais de um instalado.
    """
    global _popup_filter_ref
    from PySide6.QtCore import QObject

    if _popup_filter_ref is not None:
        app.removeEventFilter(_popup_filter_ref)
        _popup_filter_ref.deleteLater()
        _popup_filter_ref = None

    raio_painel, raio_card, _raio_controle = RADII[variant.radius]
    mask = _PopupCornerMask(radius_dialog=raio_painel, radius_menu=raio_card)

    class _Filter(QObject):
        def eventFilter(self, obj, event) -> bool:  # noqa: N802
            return mask(obj, event)

    _popup_filter_ref = _Filter(app)
    app.installEventFilter(_popup_filter_ref)
