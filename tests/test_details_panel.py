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
