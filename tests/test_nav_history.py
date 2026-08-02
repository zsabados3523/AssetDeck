"""Pilha de navegação (Fatia 32) — lógica pura, sem Qt."""

import pytest

from assetdeck.ui.nav_history import NavHistory


def test_comeca_na_raiz_sem_para_onde_ir():
    h = NavHistory()
    assert h.current() == ""
    assert h.can_back() is False
    assert h.can_forward() is False


def test_navegar_e_voltar():
    h = NavHistory()
    h.push("A")
    h.push("A/B")

    assert h.can_back() is True
    assert h.back() == "A"
    assert h.back() == ""
    assert h.can_back() is False


def test_avancar_refaz_o_caminho():
    h = NavHistory()
    h.push("A")
    h.push("A/B")
    h.back()
    h.back()

    assert h.forward() == "A"
    assert h.forward() == "A/B"
    assert h.can_forward() is False


def test_navegar_do_meio_descarta_o_futuro():
    """Comportamento de navegador: voltar e ir pra outro lugar apaga o
    caminho que estava à frente."""
    h = NavHistory()
    h.push("A")
    h.push("A/B")
    h.back()  # está em "A", com "A/B" no futuro
    h.push("C")

    assert h.current() == "C"
    assert h.can_forward() is False
    assert h.back() == "A"


def test_push_da_mesma_pasta_nao_duplica():
    """Clicar de novo na pasta já aberta não é navegação."""
    h = NavHistory()
    h.push("A")
    h.push("A")

    assert h.back() == ""
    assert h.can_back() is False


def test_back_e_forward_alem_do_limite_levantam():
    """Erro alto, nunca silencioso — quem chama checa can_* antes."""
    h = NavHistory()
    with pytest.raises(IndexError):
        h.back()
    with pytest.raises(IndexError):
        h.forward()


def test_replace_current_troca_sem_criar_navegacao():
    h = NavHistory()
    h.push("A")
    h.replace_current("")  # pasta sumiu do disco

    assert h.current() == ""
    assert h.back() == ""  # a entrada anterior segue lá
    assert h.can_back() is False
