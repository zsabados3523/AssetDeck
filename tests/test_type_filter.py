"""TypeFilter: checklist de tipos + checklist secundário de extensão (Fatia 31).

Mesmo contrato multi-seleção de sempre; a novidade é que um tipo marcado
com mais de uma extensão presente na biblioteca ganha um checklist
indentado de extensões, só visível enquanto o tipo pai estiver marcado.
"""

import pytest

from assetdeck.ui.type_filter import TypeFilter

EXT_POR_TIPO = {"model": ["fbx", "obj"], "hdri": ["hdr"]}


@pytest.fixture
def filtro(qapp):
    f = TypeFilter()
    f.reload(["model", "hdri"], EXT_POR_TIPO)
    return f


def test_sem_selecao_nao_mostra_extensao(filtro):
    assert filtro.selected() == []
    assert filtro.selected_extensions() == []


def test_tipo_com_uma_extensao_so_nao_ganha_checklist(filtro):
    # 'hdri' só tem 'hdr' na biblioteca — não tem sentido filtrar por extensão
    assert "hdri" not in filtro._ext_checks


def test_marcar_tipo_e_extensao(filtro):
    filtro._checks["model"].setChecked(True)
    filtro._ext_checks["model"]["fbx"].setChecked(True)

    assert filtro.selected() == ["model"]
    assert filtro.selected_extensions() == ["fbx"]


def test_extensao_marcada_some_se_o_tipo_pai_desmarcar(filtro):
    """Extensão fica com o checkbox tecnicamente marcado, mas não conta
    pro filtro se o tipo pai foi desmarcado (evita restringir os OUTROS
    tipos por engano)."""
    filtro._checks["model"].setChecked(True)
    filtro._ext_checks["model"]["fbx"].setChecked(True)
    filtro._checks["model"].setChecked(False)

    assert filtro.selected_extensions() == []


def test_container_de_extensao_visivel_so_com_tipo_marcado(filtro):
    # isHidden() reflete o pedido explícito de setVisible; isVisible() exigiria
    # a hierarquia toda (menu aberto de verdade) — não dá num teste headless.
    container = filtro._ext_containers["model"]
    assert container.isHidden() is True
    filtro._checks["model"].setChecked(True)
    assert container.isHidden() is False
    filtro._checks["model"].setChecked(False)
    assert container.isHidden() is True


def test_set_selected_e_set_selected_extensions_restauram_sem_emitir_changed(filtro):
    recebidos = []
    filtro.changed.connect(lambda: recebidos.append(1))

    filtro.set_selected(["model"])
    filtro.set_selected_extensions(["obj"])

    assert filtro.selected() == ["model"]
    assert filtro.selected_extensions() == ["obj"]
    assert recebidos == []
    assert filtro._ext_containers["model"].isHidden() is False


def test_limpar_desmarca_tipos_e_extensoes(filtro):
    filtro._checks["model"].setChecked(True)
    filtro._ext_checks["model"]["fbx"].setChecked(True)

    filtro._clear()

    assert filtro.selected() == []
    assert filtro.selected_extensions() == []
    assert filtro._ext_containers["model"].isHidden() is True


def test_reload_preserva_selecao_de_tipo_e_extensao(filtro):
    filtro._checks["model"].setChecked(True)
    filtro._ext_checks["model"]["fbx"].setChecked(True)

    filtro.reload(["model", "hdri"], EXT_POR_TIPO)

    assert filtro.selected() == ["model"]
    assert filtro.selected_extensions() == ["fbx"]


def test_label_mostra_contagem_de_extensao(filtro):
    filtro._checks["model"].setChecked(True)
    assert filtro.text() == "Tipo: model ▾"
    filtro._ext_checks["model"]["fbx"].setChecked(True)
    assert filtro.text() == "Tipo: model (1 ext) ▾"
