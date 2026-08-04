"""DetailsPanel: botão "Checar texturas…" (Fatia 40) — só aparece pra
asset .blend presente (não sumido)."""

from pathlib import Path

import pytest

from assetdeck.ui.details_panel import DetailsPanel

ROOT = Path("/lib")


def _row(rel_path: str, missing_since=None, asset_id: int = 1) -> dict:
    return {
        "id": asset_id, "name": Path(rel_path).stem, "asset_type": "model",
        "rel_path": rel_path, "size_bytes": 1024, "notes": None,
        "missing_since": missing_since,
    }


@pytest.fixture
def painel(qapp):
    return DetailsPanel(ROOT)


def test_comeca_escondido(painel):
    # isHidden() (não isVisible()): a janela do teste nunca é mostrada de
    # verdade, e isVisible() dependeria da hierarquia toda estar na tela.
    assert painel.check_textures_btn.isHidden() is True


def test_aparece_para_blend_presente(painel):
    painel.show_asset(_row("modelo.blend"), None)
    assert painel.check_textures_btn.isHidden() is False


@pytest.mark.parametrize("rel_path", ["textura.jpg", "modelo.fbx", "projeto.rvt",
                                      "cena.usdz", "peca.abc"])
def test_some_para_outros_formatos(painel, rel_path):
    """Fatia 37: os formatos novos (.rvt/.usd*/.abc) não são arquivos
    Blender — o conceito de textura religável por caminho interno não
    se aplica a eles."""
    painel.show_asset(_row(rel_path), None)
    assert painel.check_textures_btn.isHidden() is True


def test_some_para_blend_sumido(painel):
    painel.show_asset(_row("modelo.blend", missing_since="2026-01-01"), None)
    assert painel.check_textures_btn.isHidden() is True


def test_clicar_emite_o_sinal_com_asset_id_e_caminho(painel):
    recebidos = []
    painel.check_textures_requested.connect(lambda *a: recebidos.append(a))
    painel.show_asset(_row("modelo.blend", asset_id=42), None)

    painel._request_check_textures()

    assert recebidos == [(42, str(ROOT / "modelo.blend"))]


def test_troca_de_blend_pra_outro_formato_esconde_de_novo(painel):
    painel.show_asset(_row("modelo.blend"), None)
    assert painel.check_textures_btn.isHidden() is False

    painel.show_asset(_row("textura.jpg"), None)
    assert painel.check_textures_btn.isHidden() is True


# ------------------------------------------------- layout do painel (F48) --

def test_a_moldura_da_miniatura_existe_mesmo_vazia(painel):
    """Sem asset selecionado, o topo do painel era um buraco de 200px com um
    texto boiando no meio e nada indicando que ali é o lugar da imagem."""
    assert painel.preview.objectName() == "previewTile"
    assert painel.preview.minimumHeight() >= 180


def test_a_ficha_tecnica_alinha_os_valores_a_direita(painel):
    """O QFormLayout deixava o valor começar logo depois do rótulo mais longo:
    cinco linhas com o valor em cinco posições diferentes, impossíveis de
    varrer com o olho. Alinhados à direita, viram uma coluna só."""
    from PySide6.QtCore import Qt

    for campo in (painel.f_type, painel.f_dims, painel.f_size,
                  painel.f_format, painel.f_path):
        assert campo.objectName() == "kvValue"
        assert campo.alignment() & Qt.AlignmentFlag.AlignRight


def test_so_existe_um_botao_principal_no_painel(painel):
    """Regra do tema: um botão principal por tela é o que dá hierarquia. Se
    aparecer um segundo, os dois deixam de significar "é por aqui"."""
    from PySide6.QtWidgets import QPushButton

    principais = [b for b in painel.findChildren(QPushButton)
                  if b.objectName() == "primary"]
    assert len(principais) == 1
    assert principais[0] is painel.open_file_btn


def test_o_favorito_cabe_na_largura_do_painel(painel, qapp):
    """Bug visto na tela: o favorito dividia a linha com as cinco estrelas e
    era cortado pela borda direita — 5 botões mais um botão com texto não
    cabem nos ~250px úteis do painel."""
    painel.resize(300, 700)
    painel.show()
    qapp.processEvents()

    direita_do_fav = painel.fav_btn.mapTo(painel, painel.fav_btn.rect().topRight()).x()
    assert direita_do_fav <= painel.width(), "o botão Favorito sai do painel"

    # E não divide mais a linha com as estrelas.
    y_estrelas = painel.star_btns[0].mapTo(painel, painel.star_btns[0].rect().center()).y()
    y_fav = painel.fav_btn.mapTo(painel, painel.fav_btn.rect().center()).y()
    assert y_fav > y_estrelas
    painel.close()


def test_o_tipo_aparece_com_o_rotulo_da_categoria(painel):
    """"hdri"/"pbr_set" são vocabulário de SCHEMA, não de tela — apareciam em
    minúsculas na ficha técnica. A ficha usa o mesmo rótulo da barra de
    categorias; tipo desconhecido cai no valor cru em vez de sumir."""
    painel.show_asset(dict(_row("ceu.exr"), asset_type="hdri"), None)
    assert painel.f_type.text() == "HDRIs"

    painel.show_asset(dict(_row("parede.blend"), asset_type="pbr_set"), None)
    assert painel.f_type.text() == "Materiais"

    painel.show_asset(dict(_row("x.zzz"), asset_type="tipo_novo"), None)
    assert painel.f_type.text() == "tipo_novo"
