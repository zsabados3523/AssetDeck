"""Ícones SVG (F4, Fatia 26): carregamento, recoloração e erro alto."""

import pytest

from assetdeck.ui import icons

TODOS = ("star-filled", "star-outline", "eye-off", "search", "refresh",
         "chevron-down", "check")


@pytest.mark.parametrize("nome", TODOS)
@pytest.mark.parametrize("tam", (16, 20, 32))
def test_cada_icone_carrega_em_varios_tamanhos(qapp, nome, tam):
    pix = icons.pixmap(nome, tam=tam)
    assert not pix.isNull()
    assert pix.width() == tam and pix.height() == tam
    # Tem de haver algo desenhado, não só um retângulo transparente.
    img = pix.toImage()
    algum_pixel_visivel = any(
        img.pixelColor(x, y).alpha() > 0
        for x in range(tam) for y in range(tam)
    )
    assert algum_pixel_visivel, f"{nome} renderizou vazio"


def test_icone_inexistente_explode_alto(qapp):
    with pytest.raises(FileNotFoundError, match="glifo-que-nao-existe"):
        icons.pixmap("glifo-que-nao-existe")


def test_recoloracao_pinta_os_pixels_visiveis_na_cor_pedida(qapp):
    """Só os pixels TOTALMENTE opacos precisam bater exato — a borda do traço
    tem antialiasing, então um pixel semitransparente mistura com o fundo
    transparente e sai um tom vizinho (ex.: #1B6A78), o que é esperado."""
    from PySide6.QtGui import QColor

    pix = icons.pixmap("check", cor="#1B6B78", tam=24)
    img = pix.toImage()
    totalmente_opacos = [
        QColor(img.pixelColor(x, y)).name().upper()
        for x in range(24) for y in range(24)
        if img.pixelColor(x, y).alpha() == 255
    ]
    assert totalmente_opacos, "nenhum pixel totalmente opaco para conferir a cor"
    assert set(totalmente_opacos) == {"#1B6B78"}


def test_icon_devolve_qicon_nao_nulo(qapp):
    qi = icons.icon("search", cor="#000000")
    assert not qi.isNull()


def test_cache_reaproveita_o_mesmo_pixmap(qapp):
    a = icons.pixmap("refresh", cor="#333333", tam=20)
    b = icons.pixmap("refresh", cor="#333333", tam=20)
    assert a.cacheKey() == b.cacheKey()
