"""FilterButton (Fatia 28c): ícone + popup de escolha única.

Mesmo contrato do TypeFilter (ver test_main_window.py), só que pra valor
único em vez de multi-seleção — nota mínima e resolução mínima.
"""

import pytest

from assetdeck.ui.filter_button import FilterButton

OPCOES = [("Nota: todas", None), ("★ ≥ 1", 1), ("★ ≥ 3", 3), ("★ ≥ 5", 5)]


@pytest.fixture
def botao(qapp):
    return FilterButton("star-filled", OPCOES)


def test_valor_inicial_e_o_primeiro_das_opcoes(botao):
    assert botao.value() is None
    assert botao.isChecked() is False  # padrão não conta como "filtro ativo"


def test_escolher_uma_opcao_muda_o_valor_e_emite_changed(botao):
    recebidos = []
    botao.changed.connect(lambda: recebidos.append(botao.value()))

    acao_3 = next(acao for acao, v in botao._acoes if v == 3)
    acao_3.trigger()

    assert botao.value() == 3
    assert recebidos == [3]
    assert botao.isChecked() is True  # filtro não-padrão ativo — se destaca


def test_set_value_nao_emite_changed(botao):
    recebidos = []
    botao.changed.connect(lambda: recebidos.append(botao.value()))

    botao.set_value(5)

    assert botao.value() == 5
    assert recebidos == []
    assert botao.isChecked() is True


def test_set_value_de_volta_ao_padrao_desmarca(botao):
    botao.set_value(3)
    assert botao.isChecked() is True
    botao.set_value(None)
    assert botao.isChecked() is False


def test_tooltip_reflete_a_opcao_atual(botao):
    assert botao.toolTip() == "Nota: todas"
    botao.set_value(1)
    assert botao.toolTip() == "★ ≥ 1"


def test_apenas_uma_acao_marcada_por_vez(botao):
    """QActionGroup exclusivo: escolher uma desmarca as outras."""
    a1 = next(a for a, v in botao._acoes if v == 1)
    a3 = next(a for a, v in botao._acoes if v == 3)

    a1.trigger()
    assert a1.isChecked() and not a3.isChecked()

    a3.trigger()
    assert a3.isChecked() and not a1.isChecked()


OPCOES_COR = [("Cor: todas", None), ("Vermelho", "#c0392b"), ("Azul", "#2980b9")]


def test_swatch_da_icone_de_cor_as_opcoes_com_valor(qapp):
    botao = FilterButton("palette", OPCOES_COR, swatch=True)
    for acao, valor in botao._acoes:
        if valor is None:
            assert acao.icon().isNull()
        else:
            assert not acao.icon().isNull()


def test_sem_swatch_nenhuma_opcao_ganha_icone(qapp):
    botao = FilterButton("palette", OPCOES_COR, swatch=False)
    for acao, _valor in botao._acoes:
        assert acao.icon().isNull()
