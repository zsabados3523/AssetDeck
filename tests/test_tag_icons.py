"""Render de ícone de tag (Fatia 33) — a função que os 3 pontos de
exibição compartilham."""

import logging

import pytest
from PySide6.QtGui import QColor

from assetdeck.ui import icons, tag_icons


def test_todo_preset_tem_svg_no_disco():
    """Trava contra entrada órfã na lista (nome que não virou arquivo)."""
    for ti in tag_icons.TODOS:
        assert (icons.ICONS_DIR / f"{ti.key}.svg").exists(), f"{ti.key} sem SVG"


def test_presets_nao_tem_chave_repetida():
    chaves = [ti.key for ti in tag_icons.TODOS]
    assert len(chaves) == len(set(chaves))


def test_sem_icone_cai_no_quadradinho_da_cor(qapp):
    pix = tag_icons.pixmap_for(None, "#B05A1E", tam=12)
    assert pix.size().width() == 12
    assert QColor(pix.toImage().pixelColor(6, 6)).name().upper() == "#B05A1E"


def test_sem_icone_e_sem_cor_usa_o_cinza_do_tema(qapp):
    from assetdeck.ui import theme

    pix = tag_icons.pixmap_for(None, None, tam=12)
    assert QColor(pix.toImage().pixelColor(6, 6)).name().upper() == theme.TEXT_MUTED.upper()


def test_com_icone_desenha_o_svg_tingido(qapp):
    """O glifo assume a cor da tag — só pixels totalmente opacos batem
    exato, a borda tem antialiasing (mesmo critério de test_icons.py)."""
    pix = tag_icons.pixmap_for("tag-estrela", "#1B6B78", tam=24)
    img = pix.toImage()
    opacos = {QColor(img.pixelColor(x, y)).name().upper()
              for x in range(24) for y in range(24)
              if img.pixelColor(x, y).alpha() == 255}
    assert opacos == {"#1B6B78"}
    # e sobrou transparência: não virou um quadrado chapado
    assert any(img.pixelColor(x, y).alpha() == 0
               for x in range(24) for y in range(24))


def test_icone_que_sumiu_do_disco_cai_no_quadradinho_e_avisa(qapp, caplog):
    """Um SVG removido não pode derrubar o reload da árvore inteira — mas
    também não pode passar batido (regra: nenhum except silencioso)."""
    with caplog.at_level(logging.WARNING):
        pix = tag_icons.pixmap_for("tag-que-nao-existe", "#B05A1E", tam=12)

    assert QColor(pix.toImage().pixelColor(6, 6)).name().upper() == "#B05A1E"
    assert "tag-que-nao-existe" in caplog.text


@pytest.mark.parametrize("ti", tag_icons.TODOS, ids=lambda t: t.key)
def test_cada_preset_renderiza_visivel_em_12px(qapp, ti):
    """12px é o tamanho real na árvore: glifo detalhado demais some."""
    img = tag_icons.pixmap_for(ti.key, "#000000", tam=12).toImage()
    visiveis = sum(1 for x in range(12) for y in range(12)
                   if img.pixelColor(x, y).alpha() > 0)
    assert visiveis >= 8, f"{ti.key} quase sumiu em 12px ({visiveis} pixels)"
