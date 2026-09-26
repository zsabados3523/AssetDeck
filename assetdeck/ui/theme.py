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
# Direção visual aprovada nos mockups: branco puro no tema claro e identidade
# monocromática nos dois modos. A escala neutra serve a foco, seleção e ações
# ativas; aviso, erro e sucesso mantêm cores semânticas próprias. Contrastes
# continuam travados em `tests/test_theme.py`.

BG = "#FFFFFF"          # fundo da janela: branco (Fatia 95). Era um cinza
                        # muito claro, pra separar do painel branco por
                        # tom. O Rafael pediu branco: "as janelas já têm
                        # sombra e linha, tem contraste" — e têm mesmo,
                        # a borda e a sombra do card seguram sozinhas.
SURFACE = "#FFFFFF"     # painel/card/lateral: branco flutuando sobre o fundo
BG_TINT = "#EDEDF1"     # variação do fundo (trilho de barra de rolagem, cabeçalho)
FIELD = "#F2F2F6"       # campo de entrada: afunda em vez de sumir no branco

ACCENT = "#202124"
ACCENT_HOVER = "#38393D"
ACCENT_PRESS = "#111214"
ON_ACCENT = "#FFFFFF"
# Pastilha suave do estado ativo: cinza claro com texto quase preto.
ACCENT_SOFT = "#E8E8EA"

TITLE = "#101116"       # títulos: mais escuros que o corpo, é o que dá hierarquia
TEXT = "#1F2024"
TEXT_MUTED = "#6B6C74"
TEXT_DISABLED = "#A9AAB2"

WARNING = "#8A5A12"     # substitui o "#b07d2b" que estava inline no details_panel
DANGER = "#A32D2D"
OK = "#1F8A53"          # LED do Blender conectado no rodapé (Fatia 46)

POPOVER = "#FFFFFF"     # menus e popups são JANELAS separadas: sempre opacos
BORDER = (0, 0, 0, 0.09)         # contorno de campo/botão
BORDER_STRONG = (0, 0, 0, 0.28)  # contorno de controle (caixa de checkbox)
FOCUS = ACCENT                   # anel de foco segue a identidade monocromática

# Seleção monocromática: pastilha de cinza claro com o texto normal por cima.
# Continua sem cor de propósito — a seleção da GRADE compete com a miniatura,
# e azul atrás de uma textura suja a leitura da imagem. Cor de estado ativo é
# `ACCENT_SOFT`, usado onde não há imagem embaixo (lateral, filtros).
SELECTION = (0, 0, 0, 0.065)
HOVER = (0, 0, 0, 0.035)

# Fundo do card da grade em hover/clique (Fatia 74).
#
# ISTO ERA UMA SOMBRA e não é mais. A Fatia 74 tentou primeiro sombra
# pintada à mão (elevação estilo dashboard, como nas referências que o
# Rafael mandou), e ela falhou por DOIS motivos concretos, os dois vistos
# por ele na tela real ("quando passo o mouse por cima ela escurece tudo...
# parece cortar abruptamente por conta do limite de seu grid"):
#
#  1. O `QListView` RECORTA a pintura do delegate no retângulo da célula.
#     Uma sombra suave precisa vazar ~10-20px pra fora do card; aqui só há
#     `CARD_MARGIN` (3px) de folga antes da borda da célula. O resto era
#     cortado em linha reta — daí o "corte abrupto".
#  2. As camadas da sombra eram retângulos PREENCHIDOS crescendo pra fora;
#     como o card não pinta fundo opaco por cima, elas escureciam também o
#     MIOLO do card (a área de respiro em volta da miniatura). Daí o
#     "escurece tudo".
#
# Aumentar `CARD_MARGIN` até caber uma sombra de verdade engordaria TODA
# célula da grade — menos assets por tela, num app cuja biblioteca real tem
# 72 mil. Não compensa. Então a elevação passou a ser dada por um FUNDO
# sólido que aparece só sob o cursor (mais um degrau de 2px pra cima),
# inteiramente DENTRO do card: nada pra recortar, nada pra escurecer.
#
# Os tons são um degrau a partir de `surface` (o painel onde a grade mora):
# no claro escurecem de leve, no escuro clareiam — em ambos o elemento lê
# como "levantado" em relação ao painel. Neutros de propósito, nunca a cor
# de destaque: o mesmo motivo já registrado em SELECTION logo acima — cor
# atrás de uma miniatura suja a leitura da imagem.
#
# Não são só do card (Fatia 75): BOTÃO e outros controles usam o MESMO
# degrau pra hover/clique. Antes cada controle usava `$surface_hover`, que é
# o véu de 3,5% de preto — quase invisível, e a razão de o app inteiro
# parecer não responder ao mouse. Um degrau só, compartilhado, é o que faz
# "levantado" e "afundado" quererem dizer a mesma coisa em qualquer lugar da
# tela; por isso o nome é do ESTADO (raised/sunken), não do widget.
SURFACE_RAISED = "#EFEFF4"
SURFACE_SUNKEN = "#E4E4EB"

# Fundo do card quando o asset não tem miniatura. Segue NEUTRO de propósito,
# mesmo agora que existe cor de destaque: é uma pastilha que aparece dezenas de
# vezes na grade ao mesmo tempo, e pintá-la de azul transformaria a ausência de
# miniatura no elemento mais gritante da tela. O reconhecimento do tipo vem do
# rótulo de extensão no canto (".fbx"/".exr"/...), não de cor. Antes isto era
# um apelido de ACCENT; virou constante própria justamente para o azul não
# vazar até aqui. Consumido pelo delegate (Fatia 27).
TYPE_TINT = "#EDEDF1"
ON_TYPE_TINT = "#303136"  # texto/glifo sobre a pastilha acima

# --------------------------------------------------------------------------
# Paleta escura (Fatia 43)
# --------------------------------------------------------------------------
# O modo escuro preserva a hierarquia de quase-preto em camadas. O destaque
# inverte para cinza muito claro com texto escuro; os tons semânticos ficam
# mais claros para continuar legíveis sobre superfícies escuras.

BG_DARK = "#101114"
SURFACE_DARK = "#1A1B1F"
BG_TINT_DARK = "#232429"
# No escuro o campo AFUNDA em vez de subir: um input mais claro que o painel
# parece um botão. É o inverso do modo claro, onde o campo é o cinza e o painel
# é o branco — por isso `field` é token próprio e não um apelido de `bg`.
FIELD_DARK = "#131417"

ACCENT_DARK = "#F0F0F2"
ACCENT_HOVER_DARK = "#FFFFFF"
ACCENT_PRESS_DARK = "#D5D5D8"
ON_ACCENT_DARK = "#17181B"
ACCENT_SOFT_DARK = "#38393D"

TITLE_DARK = "#FFFFFF"
TEXT_DARK = "#DEDEE3"
TEXT_MUTED_DARK = "#8C8D95"
TEXT_DISABLED_DARK = "#5C5C62"

WARNING_DARK = "#E3B15C"
DANGER_DARK = "#E2726F"
OK_DARK = "#4EC98A"

POPOVER_DARK = "#1F2024"
BORDER_DARK = (255, 255, 255, 0.10)
BORDER_STRONG_DARK = (255, 255, 255, 0.26)
FOCUS_DARK = ACCENT_DARK

SELECTION_DARK = (255, 255, 255, 0.09)
HOVER_DARK = (255, 255, 255, 0.06)

# Degraus de elevação no escuro (Fatia 74/75) — ver `SURFACE_RAISED` acima
# pro porquê de isto não ser uma sombra. Aqui os tons CLAREIAM a partir de
# `SURFACE_DARK` (#1A1B1F): no escuro, "levantado" é mais claro, não mais
# escuro — sombra preta sobre fundo quase preto não rende nada (mesmo
# problema já registrado em `apply_card_shadow()`).
SURFACE_RAISED_DARK = "#24252B"
SURFACE_SUNKEN_DARK = "#2C2D34"

# Mesma decisão do modo claro: pastilha neutra, não azul (ver TYPE_TINT). Aqui
# ela é ESCURA com texto claro por cima — no escuro, a pastilha cinza-clara que
# havia antes acendia a grade inteira onde faltava miniatura.
TYPE_TINT_DARK = "#2C2D33"
ON_TYPE_TINT_DARK = "#DEDEE3"

# Nomes internos (não $token do QSS) usados por `_paleta()` pra trocar de
# bloco inteiro conforme `variant.mode`, sem duplicar build_tokens/
# build_palette/surface_solid em duas versões.
_PALETA_CLARA = {
    "bg": BG, "surface": SURFACE, "bg_tint": BG_TINT, "field": FIELD,
    "accent": ACCENT, "accent_hover": ACCENT_HOVER, "accent_press": ACCENT_PRESS,
    "on_accent": ON_ACCENT, "accent_soft": ACCENT_SOFT,
    "title": TITLE, "text": TEXT, "text_muted": TEXT_MUTED, "text_disabled": TEXT_DISABLED,
    "warning": WARNING, "danger": DANGER, "ok": OK,
    "popover": POPOVER, "border": BORDER, "border_strong": BORDER_STRONG, "focus": FOCUS,
    "selection": SELECTION, "hover": HOVER,
    "surface_raised": SURFACE_RAISED, "surface_sunken": SURFACE_SUNKEN,
    "type_tint": TYPE_TINT, "on_type_tint": ON_TYPE_TINT,
}
_PALETA_ESCURA = {
    "bg": BG_DARK, "surface": SURFACE_DARK, "bg_tint": BG_TINT_DARK, "field": FIELD_DARK,
    "accent": ACCENT_DARK, "accent_hover": ACCENT_HOVER_DARK, "accent_press": ACCENT_PRESS_DARK,
    "on_accent": ON_ACCENT_DARK, "accent_soft": ACCENT_SOFT_DARK,
    "title": TITLE_DARK, "text": TEXT_DARK, "text_muted": TEXT_MUTED_DARK,
    "text_disabled": TEXT_DISABLED_DARK,
    "warning": WARNING_DARK, "danger": DANGER_DARK, "ok": OK_DARK,
    "popover": POPOVER_DARK, "border": BORDER_DARK, "border_strong": BORDER_STRONG_DARK,
    "focus": FOCUS_DARK,
    "selection": SELECTION_DARK, "hover": HOVER_DARK,
    "surface_raised": SURFACE_RAISED_DARK, "surface_sunken": SURFACE_SUNKEN_DARK,
    "type_tint": TYPE_TINT_DARK, "on_type_tint": ON_TYPE_TINT_DARK,
}


def _paleta(mode: str) -> dict:
    return _PALETA_ESCURA if mode == "escuro" else _PALETA_CLARA


# Variações que o Rafael escolhe na tela (vitrine da Fatia 24).
# Fundo e painel são os DOIS brancos: o que separa um do outro é uma linha de
# contorno quase invisível mais uma sombra de opacidade baixa. Este número é a
# opacidade dessa linha — é o único ajuste de "quanto o painel se destaca".
SEPARATION = {"sutil": 0.05, "media": 0.075, "forte": 0.11}
RADII = {  # (painel, card, controle)
    "discreto": (10, 8, 6),
    # Cantos marcantes compõem a identidade aprovada nos mockups.
    "marcante": (20, 16, 10),
}
FONTS = {
    "manrope": "Manrope",
    "inter": "Inter",
    "sistema": "",  # vazio = mantém a fonte padrão do sistema
}
DISPLAY_FONT = "Manrope"

# A fonte da prévia aprovada acompanha o app. Arquivos estáticos separados
# fazem o Qt reconhecer os pesos que a interface usa, sem síntese de negrito.
MANROPE_FONT_FILES = {
    "Regular": Path(__file__).parent / "fonts" / "Manrope-Regular.ttf",
    "Medium": Path(__file__).parent / "fonts" / "Manrope-Medium.ttf",
    "SemiBold": Path(__file__).parent / "fonts" / "Manrope-SemiBold.ttf",
    "Bold": Path(__file__).parent / "fonts" / "Manrope-Bold.ttf",
}

BACKGROUNDS = ("liso", "grao")
MODES = ("claro", "escuro")


@dataclass(frozen=True)
class Variant:
    """Uma combinação de escolhas visuais.

    O padrão é o que o Rafael pediu: fundo liso, translucidez média, cantos
    marcantes, fonte Manrope, modo claro. A vitrine (`theme_gallery.py`) troca
    estes campos ao vivo para ele comparar as alternativas na tela antes de
    bater o martelo.
    """

    background: str = "liso"      # liso | grao
    separation: str = "media"     # sutil | media | forte (opacidade da linha)
    radius: str = "discreto"     # discreto | marcante
    font: str = "manrope"         # manrope | inter | sistema
    mode: str = "claro"           # claro | escuro (Fatia 43)

    def __post_init__(self) -> None:
        for campo, valor, validos in (
            ("background", self.background, BACKGROUNDS),
            ("separation", self.separation, tuple(SEPARATION)),
            ("radius", self.radius, tuple(RADII)),
            ("font", self.font, tuple(FONTS)),
            ("mode", self.mode, MODES),
        ):
            if valor not in validos:
                raise ValueError(
                    f"Variant.{campo}={valor!r} é inválido; use um de {validos}."
                )


DEFAULT = Variant()

# Widgets que pintam cor "à mão" em Python (delegate de item, ícones
# pré-tingidos) não passam pelo QSS — o `$token` não alcança `QPainter`
# direto. Pra esses casos saberem qual modo está ativo AGORA (sem cada um
# ter que receber `Variant` por fora), `apply_theme()` guarda o último
# aplicado aqui. Consumido por `current_colors()` abaixo (Fatia 43).
_CURRENT_VARIANT = DEFAULT


def current_variant() -> Variant:
    """O último `Variant` passado pra `apply_theme()` nesta sessão."""
    return _CURRENT_VARIANT


def current_colors() -> dict:
    """Paleta (claro/escuro) do `Variant` atualmente aplicado — pra código
    Python que pinta cor direto (delegate, ícone pré-tingido), sem QSS."""
    return _paleta(_CURRENT_VARIANT.mode)


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

    fundo = _paleta(variant.mode)["bg"]
    assinatura = f"{fundo}-{TILE}-{GRAIN_SIGMA}-{GRAIN_SEED}"
    nome = f"bg-{hashlib.sha1(assinatura.encode()).hexdigest()[:12]}.png"
    destino = config.cache_dir() / "theme" / nome
    if destino.exists():
        return destino

    import numpy as np
    from PySide6.QtGui import QImage

    destino.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(GRAIN_SEED)
    base = np.array(hex_to_rgb(fundo), dtype=np.float32)
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
    """Cor do painel — a superfície onde o texto realmente cai.

    Até a Fatia 43 devolvia o próprio fundo: painel e janela eram a mesma cor,
    separados só por uma linha. Na Fatia 44 passaram a diferir (branco sobre
    cinza claro; #16171A sobre #101114), e é por isso que esta função existe
    separada de `bg` — é contra ELA que `tests/test_theme.py` mede o contraste
    de todo texto.
    """
    return _paleta(variant.mode)["surface"]


def build_tokens(variant: Variant = DEFAULT) -> dict[str, str]:
    """Todos os `$nome` que o theme.qss pode usar."""
    pal = _paleta(variant.mode)
    raio_painel, raio_card, raio_controle = RADII[variant.radius]
    familia = FONTS[variant.font]
    ladrilho = background_tile_path(variant)
    bg_image = ""
    if ladrilho is not None:
        # Caminho ABSOLUTO — url() relativo resolve contra o cwd e falha calado.
        bg_image = f"background-image: url({ladrilho});\n    background-repeat: repeat;"

    # Hairline (linha de separação painel/fundo): preto translúcido sobre
    # fundo claro, branco translúcido sobre fundo escuro — mesma ideia de
    # SELECTION/HOVER, que já trocam de base por modo na paleta acima.
    base_hairline = (0, 0, 0) if variant.mode == "claro" else (255, 255, 255)

    return {
        "bg": pal["bg"],
        "bg_tint": pal["bg_tint"],
        "bg_image": bg_image,

        "surface": pal["surface"],
        "surface_hover": rgba_css(pal["hover"]),
        # Degraus de elevação (Fatia 75) — os MESMOS que o card da grade usa,
        # agora também para botões e controles. Ver `SURFACE_RAISED`.
        "surface_raised": pal["surface_raised"],
        "surface_sunken": pal["surface_sunken"],
        "type_tint": pal["type_tint"],
        "on_type_tint": pal["on_type_tint"],
        "selection": rgba_css(pal["selection"]),
        "field": pal["field"],
        "popover": pal["popover"],

        "border": rgba_css(pal["border"]),
        "border_strong": rgba_css(pal["border_strong"]),
        "hairline": rgba_css((*base_hairline, separation_alpha(variant))),
        "focus": pal["focus"],

        "accent": pal["accent"],
        "accent_hover": pal["accent_hover"],
        "accent_press": pal["accent_press"],
        "on_accent": pal["on_accent"],
        "accent_soft": pal["accent_soft"],

        "title": pal["title"],
        "text": pal["text"],
        "text_muted": pal["text_muted"],
        "text_disabled": pal["text_disabled"],
        "warning": pal["warning"],
        "danger": pal["danger"],
        "ok": pal["ok"],

        "radius_panel": f"{raio_painel}px",
        "radius_card": f"{raio_card}px",
        "radius_control": f"{raio_controle}px",
        # Pastilha (Fatia 76): pontas em semicírculo nos botões de categoria e
        # de filtro. O valor tem de ser CONCRETO e no máximo METADE da altura
        # do botão — descoberto na marra: o Qt não aceita `50%`, e quando o
        # raio passa da metade da altura ele DESCARTA a regra inteira em
        # silêncio, deixando o canto reto (a 1ª tentativa usou `999px`
        # justamente pra "deixar o Qt cortar", e o resultado foi botão
        # quadrado). Medido com os botões reais: categoria 39px de altura,
        # filtro 37px — 18px é a metade do menor. `test_theme.py` falha se
        # algum deles encolher a ponto de o raio parar de valer.
        "radius_pill": "18px",
        # Pastilha PEQUENA: seletor de biblioteca e controles do visualizador
        # 3D (Fatia 94/95). Precisa de token próprio porque o raio tem de
        # caber na metade da altura — 18px numa pastilha de 26px faz o Qt
        # descartar o arredondamento inteiro, sem erro nenhum.
        "radius_pill_small": "13px",
        "radius_chip_small": "9px",
        "radius_brand_tile": "2px",
        "radius_slider_handle": "9px",

        "pad_s": "4px",
        "pad_m": "8px",
        "pad_l": "12px",

        "font_family": f'"{familia}"' if familia else "inherit",
        "font_family_display": (
            f'"{DISPLAY_FONT}"' if familia else "inherit"
        ),
        "font_size": "13px",
        "font_size_small": "11px",
        "font_size_title": "17px",
        "font_size_brand": "16px",
        "font_size_page_title": "25px",

        "check_icon": str(icon_asset_path("check", pal["on_accent"], 12)),
        "chevron_icon": str(icon_asset_path("chevron-down", pal["text_muted"], 12)),
        # Setas da árvore (Fatia 78). Existem porque zerar o fundo do
        # `QTreeView::branch` — necessário pra pastilha do item não ganhar um
        # bloco quadrado ao lado — APAGA as setas que o Fusion desenhava (a
        # regra 2 do cabeçalho do `theme.qss`, confirmada na tela). Repondo
        # aqui, o `::branch` pode ficar sem fundo sem perder o indicador.
        "branch_closed_icon": str(icon_asset_path("chevron-right", pal["text_muted"], 10)),
        "branch_open_icon": str(icon_asset_path("chevron-down", pal["text_muted"], 10)),
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

    pal = _paleta(variant.mode)
    p = QPalette()
    superficie = QColor(surface_solid(variant))
    C = QColor

    p.setColor(QPalette.ColorRole.Window, C(pal["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, C(pal["text"]))
    p.setColor(QPalette.ColorRole.Base, superficie)
    p.setColor(QPalette.ColorRole.AlternateBase, C(pal["bg_tint"]))
    p.setColor(QPalette.ColorRole.Text, C(pal["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, C(pal["text_disabled"]))
    p.setColor(QPalette.ColorRole.Button, superficie)
    p.setColor(QPalette.ColorRole.ButtonText, C(pal["text"]))
    p.setColor(QPalette.ColorRole.BrightText, C(pal["danger"]))
    p.setColor(QPalette.ColorRole.Highlight, C(pal["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, C(pal["on_accent"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, C(pal["popover"]))
    p.setColor(QPalette.ColorRole.ToolTipText, C(pal["text"]))
    p.setColor(QPalette.ColorRole.Link, C(pal["accent"]))

    for grupo in (QPalette.ColorGroup.Disabled,):
        p.setColor(grupo, QPalette.ColorRole.Text, C(pal["text_disabled"]))
        p.setColor(grupo, QPalette.ColorRole.WindowText, C(pal["text_disabled"]))
        p.setColor(grupo, QPalette.ColorRole.ButtonText, C(pal["text_disabled"]))
    return p


def apply_card_shadow(widget) -> None:
    """Sombra pro painel "flutuar" sobre o fundo.

    Custo medido: repaint ~2,3x mais caro. Por isso vale em painel estático,
    mas NUNCA no container da grade — ela rola com centenas de itens e o efeito
    força o Qt a renderizar a subárvore inteira fora da tela a cada quadro.

    Presença aumentada na Fatia 43 (pedido do Rafael, "mais confiante" que o
    sutil original) — mais notável sobretudo no modo claro; no escuro, sombra
    preta sobre fundo já escuro quase não aparece, e a elevação ali vem mais
    do contorno/tom do `$popover` do que da sombra (esperado, não é bug).
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    efeito = QGraphicsDropShadowEffect(widget)
    efeito.setBlurRadius(24)
    efeito.setXOffset(0)
    efeito.setYOffset(3)
    efeito.setColor(QColor(0, 0, 0, 42))  # cinza neutro, sem cor
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
    if variant.font == "manrope" and not app.property("assetdeck_manrope_font_registered"):
        font_ids = []
        for style, font_file in MANROPE_FONT_FILES.items():
            if not font_file.is_file():
                log.error("Fonte Manrope %s não encontrada em %s", style, font_file)
                continue
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            if font_id < 0:
                log.error("Qt não conseguiu registrar a fonte Manrope %s em %s", style, font_file)
                continue
            familias_registradas = QFontDatabase.applicationFontFamilies(font_id)
            if familia not in familias_registradas:
                log.error(
                    "A fonte em %s registrou as famílias %s; esperava %r.",
                    font_file, familias_registradas, familia,
                )
                continue
            font_ids.append(font_id)

        app.setProperty("assetdeck_manrope_font_ids", font_ids)
        app.setProperty("assetdeck_manrope_font_registered", True)
        estilos_disponiveis = set(QFontDatabase.styles(familia))
        estilos_esperados = set(MANROPE_FONT_FILES)
        if estilos_faltantes := estilos_esperados - estilos_disponiveis:
            log.error(
                "Estilos Manrope ausentes após registro: %s (disponíveis: %s)",
                sorted(estilos_faltantes), sorted(estilos_disponiveis),
            )
    if familia:
        if familia in QFontDatabase.families():
            fonte = QFont(familia)
            fonte.setPointSize(10)
            app.setFont(fonte)
        else:
            log.warning(
                "Fonte %r não está instalada; usando a fonte padrão do sistema.", familia
            )
    if familia and DISPLAY_FONT not in QFontDatabase.families():
        log.warning(
            "Fonte de títulos %r não está instalada; usando o fallback do Qt.",
            DISPLAY_FONT,
        )

    app.setPalette(build_palette(variant))
    app.setStyleSheet(build_qss(variant))
    install_popup_corner_mask(app, variant)

    global _CURRENT_VARIANT
    _CURRENT_VARIANT = variant

    log.info(
        "Tema aplicado (modo=%s, fundo=%s, separação=%s, cantos=%s, fonte=%s).",
        variant.mode, variant.background, variant.separation, variant.radius, variant.font,
    )


class _PopupCornerMask:
    """Prepara diálogos e registra que os cantos são desenhados pelo tema.

    Máscaras de QWidget recortam em pixels inteiros e deixam os cantos
    serrilhados. O QSS já desenha os raios de QMenu e a base de QDialog com
    antialiasing; o filtro fica apenas com a padronização das QMessageBox.
    """

    def __call__(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QMenu

        if event.type() != QEvent.Type.Show:
            return False
        if isinstance(obj, QMenu):
            obj.setProperty("_assetdeck_corner_renderer", "qss")
        elif isinstance(obj, QDialog):
            self._prepare_dialog(obj, QDialogButtonBox, QMessageBox)
            obj.setProperty("_assetdeck_corner_renderer", "qss")
        return False

    @staticmethod
    def _prepare_dialog(dialog, button_box_type, message_box_type) -> None:
        """Aplica a faixa de ações comum e rótulos em português."""
        from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

        if isinstance(dialog, QMessageBox) and not dialog.objectName():
            dialog.setObjectName("assetdeckMessageBox")

        textos = {
            QDialogButtonBox.StandardButton.Ok: "OK",
            QDialogButtonBox.StandardButton.Cancel: "Cancelar",
            QDialogButtonBox.StandardButton.Close: "Fechar",
            QDialogButtonBox.StandardButton.Yes: "Sim",
            QDialogButtonBox.StandardButton.No: "Não",
            QDialogButtonBox.StandardButton.Apply: "Aplicar",
            QDialogButtonBox.StandardButton.Save: "Salvar",
            QDialogButtonBox.StandardButton.Discard: "Descartar",
            QDialogButtonBox.StandardButton.Abort: "Interromper",
            QDialogButtonBox.StandardButton.Retry: "Tentar novamente",
            QDialogButtonBox.StandardButton.Ignore: "Ignorar",
            QDialogButtonBox.StandardButton.Open: "Abrir",
            QDialogButtonBox.StandardButton.Reset: "Redefinir",
            QDialogButtonBox.StandardButton.RestoreDefaults: "Restaurar padrão",
        }

        for caixa in dialog.findChildren(button_box_type):
            if not caixa.objectName():
                caixa.setObjectName("dialogActions")
            for botao in caixa.buttons():
                texto = textos.get(caixa.standardButton(botao))
                if texto:
                    botao.setText(texto)

        if isinstance(dialog, message_box_type):
            for botao in dialog.buttons():
                texto = textos.get(dialog.standardButton(botao))
                if texto:
                    botao.setText(texto)

_popup_filter_ref = None  # installEventFilter não segura referência sozinho


def install_popup_corner_mask(app, variant: Variant = DEFAULT) -> None:
    """Instala (ou reinstala) a padronização dos popups e caixas de diálogo.

    O nome é mantido para compatibilidade interna; os cantos agora são
    antisserrilhados pelo QSS e não recebem mais recorte por máscara.

    Bug pego rodando a suíte inteira: `apply_theme()` é chamado várias vezes
    em sequência em teste (`test_todas_as_variantes_aplicam_sem_erro` chama
    24x seguidas). Sem remover o filtro ANTERIOR antes de instalar o novo,
    eles se acumulavam no `QApplication` — que dura a sessão inteira de
    testes — e cada evento Show passava a ser reprocessado por dezenas de
    filtros ao mesmo tempo, travando a suíte por minutos. Por isso remove o
    filtro velho primeiro: nunca mais de um instalado.
    """
    global _popup_filter_ref
    from PySide6.QtCore import QObject

    if _popup_filter_ref is not None:
        app.removeEventFilter(_popup_filter_ref)
        _popup_filter_ref.deleteLater()
        _popup_filter_ref = None

    _ = variant  # os raios são consumidos diretamente pelo QSS do tema.
    chrome = _PopupCornerMask()

    class _Filter(QObject):
        def eventFilter(self, obj, event) -> bool:  # noqa: N802
            return chrome(obj, event)

    _popup_filter_ref = _Filter(app)
    app.installEventFilter(_popup_filter_ref)
