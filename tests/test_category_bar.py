"""CategoryBar (Fatia 31 refeita): fileira de botões por categoria.

Substitui o test_type_filter.py — o widget antigo (um botão só, sem
rótulo) foi reprovado pelo Rafael na tela.
"""

import pytest

from assetdeck.ui.categories import CATEGORIES, category_of
from assetdeck.ui.category_bar import CategoryBar

CONTAGEM = {"modelos": 85, "materiais": 127, "imagens": 148,
            "hdris": 7, "vetores": 14, "documentos": 0}
EXTS = {"modelos": {"blend": 85}, "imagens": {"jpg": 122, "png": 25, "tiff": 1}}


@pytest.fixture
def barra(qapp):
    b = CategoryBar()
    for key, botao in b.buttons.items():
        botao.reload(EXTS.get(key, {}), CONTAGEM[key])
    return b


def test_um_botao_por_categoria(barra):
    assert list(barra.buttons) == [c.key for c in CATEGORIES]


def test_botao_mostra_so_a_contagem_quando_desligado(barra):
    """Variante V3 (Fatia 46), escolhida pelo Rafael entre três esboços.

    Substitui o contrato da Fatia 31 ("botão só com ícone, nome e contagem no
    tooltip"): ele reclamou de não saber o que cada botão fazia sem passar o
    mouse. A contagem passou a ficar sempre visível; o nome, só na categoria
    ativa — a variante com todos os nomes visíveis ficou larga demais.
    """
    botao = barra.buttons["modelos"]
    assert botao.text().strip() == "85"
    assert "Modelos" not in botao.text()
    assert botao.toolTip() == "Modelos — 85 assets (todas as extensões)"


def test_botao_ganha_o_nome_quando_ligado(barra):
    botao = barra.buttons["modelos"]
    botao.setChecked(True)
    assert "Modelos" in botao.text()
    assert "85" in botao.text()

    botao.setChecked(False)
    assert "Modelos" not in botao.text()


def _imagem_do_icone(botao):
    """A IMAGEM do ícone, não o `cacheKey()`.

    `cacheKey()` é por instância de QIcon: `icons.icon()` devolve um QIcon
    novo a cada chamada, então comparar cacheKey acusa "mudou" mesmo quando a
    cor é idêntica — um teste que passa sozinho, sem provar nada.
    """
    return botao.icon().pixmap(20, 20).toImage()


def test_o_icone_acompanha_o_estado_do_botao(barra):
    """O QSS pinta o TEXTO do botão marcado de destaque, mas `color:` não
    alcança um QIcon: sem retingir em Python, a pastilha ativa ficava com o
    nome azul e o glifo cinza ao lado, parecendo desligada pela metade."""
    botao = barra.buttons["modelos"]
    desligado = _imagem_do_icone(botao)

    botao.setChecked(True)
    assert _imagem_do_icone(botao) != desligado, "o ícone não mudou de cor"

    botao.setChecked(False)
    assert _imagem_do_icone(botao) == desligado


def test_tooltip_lista_as_extensoes_marcadas(barra):
    barra.buttons["imagens"]._ext_checks["jpg"].setChecked(True)
    assert barra.buttons["imagens"].toolTip() == "Imagens — 148 assets (.jpg)"


def test_categoria_vazia_fica_desabilitada(barra):
    assert barra.buttons["documentos"].isEnabled() is False
    assert barra.buttons["modelos"].isEnabled() is True


def test_sem_selecao_nao_filtra_nada(barra):
    assert barra.selection() == []


def test_marcar_categoria_seleciona_os_tipos_dela(barra):
    barra.buttons["imagens"].setChecked(True)
    assert barra.selection() == [
        {"asset_types": ["texture", "cutout"], "extensions": []}
    ]


def test_marcar_extensao_liga_a_categoria_sozinha(barra):
    """Escolher .jpg sem a categoria ligada deixaria o filtro inerte."""
    botao = barra.buttons["imagens"]
    assert botao.isChecked() is False
    botao._ext_checks["jpg"].setChecked(True)

    assert botao.isChecked() is True
    assert barra.selection() == [
        {"asset_types": ["texture", "cutout"], "extensions": ["jpg"]}
    ]


def test_duas_categorias_ao_mesmo_tempo_nao_misturam_extensao(barra):
    barra.buttons["imagens"]._ext_checks["jpg"].setChecked(True)
    barra.buttons["modelos"].setChecked(True)

    assert barra.selection() == [
        {"asset_types": ["model", "scene"], "extensions": []},
        {"asset_types": ["texture", "cutout"], "extensions": ["jpg"]},
    ]


def test_set_selection_restaura_sem_emitir_changed(barra):
    recebidos = []
    barra.changed.connect(lambda: recebidos.append(1))

    barra.set_selection([{"asset_types": ["texture"], "extensions": ["png"]}])

    assert barra.buttons["imagens"].isChecked() is True
    assert barra.buttons["imagens"].selected_extensions() == ["png"]
    assert recebidos == []


def test_set_selection_from_types_mapeia_query_antiga(barra):
    """Smart Collection salva antes da Fatia 31 só tem asset_types crus."""
    barra.set_selection_from_types(["texture"])
    assert barra.buttons["imagens"].isChecked() is True
    assert barra.buttons["modelos"].isChecked() is False


def test_limpar_extensoes_mantem_a_categoria(barra):
    botao = barra.buttons["imagens"]
    botao._ext_checks["jpg"].setChecked(True)
    botao._clear_extensions()

    assert botao.isChecked() is True
    assert botao.selected_extensions() == []


def test_update_counts_so_mexe_no_numero(barra):
    barra.buttons["imagens"]._ext_checks["jpg"].setChecked(True)
    barra.update_counts({**CONTAGEM, "imagens": 3})

    assert barra.buttons["imagens"].toolTip() == "Imagens — 3 assets (.jpg)"
    assert barra.buttons["imagens"].selected_extensions() == ["jpg"]


def test_todo_asset_type_do_schema_cai_em_uma_categoria():
    """Trava contra tipo novo no schema ficar órfão da barra."""
    do_schema = {"texture", "pbr_set", "hdri", "cutout", "reference", "model",
                 "scene", "vector", "ies", "lut", "psd", "other"}
    for t in do_schema:
        assert category_of(t) is not None, f"{t} não tem categoria"

    cobertos = [t for c in CATEGORIES for t in c.asset_types]
    assert sorted(cobertos) == sorted(do_schema)  # nenhum tipo em duas categorias


def test_outros_programas_caem_em_modelos(qapp):
    """Fatia 37: .rvt/.skp/.usd*/.abc entram como asset_type='model' no
    scanner — prova de ponta a ponta que caem na categoria certa sem
    precisar tocar em categories.py."""
    from pathlib import Path

    from assetdeck.indexer.scanner import classify

    for nome in ("Projeto.rvt", "fachada.skp", "cena.usd", "cena.usda",
                 "cena.usdc", "cena.usdz", "anim.abc"):
        tipo = classify(Path(nome))
        assert category_of(tipo).key == "modelos", f"{nome} -> {tipo}"
