"""Preview de .svg (pedido do Rafael): rasteriza com QtSvg, sem lib nova."""

from pathlib import Path

import pytest

from assetdeck.thumbs.preview import can_preview, load_full_image, make_any_thumbnail
from assetdeck.thumbs.vector import can_vector, make_vector_thumbnail, render_vector

_SVG_ESTRELA = """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26Z" fill="#000000"/>
</svg>"""

_SVG_RETANGULO = """<svg width="400" height="100" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="100" fill="#336699"/>
</svg>"""


@pytest.fixture
def svg_quadrado(tmp_path) -> Path:
    p = tmp_path / "estrela.svg"
    p.write_text(_SVG_ESTRELA, encoding="utf-8")
    return p


@pytest.fixture
def svg_retangular(tmp_path) -> Path:
    p = tmp_path / "banner.svg"
    p.write_text(_SVG_RETANGULO, encoding="utf-8")
    return p


def test_can_vector_e_can_preview(qapp):
    assert can_vector(Path("logo.svg")) and can_vector(Path("LOGO.SVG"))
    assert not can_vector(Path("logo.png"))
    assert can_preview(Path("logo.svg"))


def test_can_preview_nao_aceita_formatos_vetoriais_sem_biblioteca(qapp):
    """.dwg/.ai/.eps/.cdr também são "vector" no scanner (asset_type), mas
    nenhum tem biblioteca disponível offline pra render — ficam sem preview,
    de propósito (explicado ao Rafael, não é bug)."""
    for ext in ("dwg", "ai", "eps", "cdr"):
        assert not can_preview(Path(f"peca.{ext}"))


def test_render_vector_produz_imagem_quadrada_com_conteudo(qapp, svg_quadrado):
    img = render_vector(svg_quadrado, size=128)
    assert img.size == (128, 128)
    assert img.mode == "RGBA"
    pixels_visiveis = sum(
        1 for x in range(0, 128, 4) for y in range(0, 128, 4)
        if img.getpixel((x, y))[3] > 0
    )
    assert pixels_visiveis > 0, "SVG renderizou vazio"


def test_render_vector_mantem_proporcao_de_svg_nao_quadrado(qapp, svg_retangular):
    """400x100 (proporção 4:1) num quadro 128x128 tem que caber sem esticar
    — a altura do desenho fica bem menor que 128, com transparência acima e
    abaixo (letterbox), não preenchendo o quadro inteiro."""
    img = render_vector(svg_retangular, size=128)
    linha_do_meio = [img.getpixel((x, 64))[3] > 0 for x in range(128)]
    linha_da_borda = [img.getpixel((x, 2))[3] > 0 for x in range(128)]
    assert any(linha_do_meio), "o retângulo devia aparecer no meio"
    assert not any(linha_da_borda), "não devia haver conteúdo colado na borda de cima"


def test_make_vector_thumbnail_grava_png_no_disco(qapp, svg_quadrado, tmp_path):
    dest = tmp_path / "thumb.png"
    make_vector_thumbnail(svg_quadrado, dest, size=96)
    assert dest.exists() and dest.stat().st_size > 0


def test_make_any_thumbnail_reconhece_svg(qapp, svg_quadrado, tmp_path):
    dest = tmp_path / "thumb2.png"
    make_any_thumbnail(svg_quadrado, dest, size=64)
    assert dest.exists()


def test_load_full_image_funciona_pra_svg(qapp, svg_quadrado):
    img = load_full_image(svg_quadrado)
    assert img.size == (1600, 1600)


def test_svg_invalido_da_erro_claro(qapp, tmp_path):
    ruim = tmp_path / "quebrado.svg"
    ruim.write_text("isto não é um XML válido <<<", encoding="utf-8")
    with pytest.raises(ValueError):
        render_vector(ruim)
