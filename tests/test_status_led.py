"""LED de status do rodapé (Fatia 49)."""

import pytest

from assetdeck.ui import theme
from assetdeck.ui.status_led import StatusLed


@pytest.fixture
def led(qapp):
    return StatusLed()


def test_comeca_inativo(led):
    assert led.estado() == "inativo"


def test_troca_de_estado_troca_a_cor(led, qapp):
    theme.apply_theme(qapp, theme.Variant(mode="claro"))
    led.refresh_theme()

    led.set_estado("ok")
    verde = led._cor.name()
    led.set_estado("erro")
    vermelho = led._cor.name()

    assert verde == theme.OK.lower()
    assert vermelho == theme.DANGER.lower()
    assert verde != vermelho


def test_estado_desconhecido_cai_em_inativo_e_loga(led, caplog):
    """Regra do projeto: nada de `except` silencioso — mas um estado errado
    também não pode derrubar a janela por causa do rodapé."""
    with caplog.at_level("ERROR"):
        led.set_estado("roxo-brilhante")
    assert led.estado() == "inativo"
    assert "roxo-brilhante" in caplog.text


def test_o_led_acompanha_a_troca_de_modo(led, qapp):
    """Pinta cor à mão, então não passa pelo QSS — cai na armadilha já
    documentada no REDESIGN-V2 e precisa de `refresh_theme()`."""
    led.set_estado("ok")

    theme.apply_theme(qapp, theme.Variant(mode="claro"))
    led.refresh_theme()
    claro = led._cor.name()

    theme.apply_theme(qapp, theme.Variant(mode="escuro"))
    led.refresh_theme()
    assert led._cor.name() != claro


def test_o_led_desenha_um_circulo_da_cor_do_estado(led, qapp):
    """Prova de PIXEL: um QWidget que não pinta nada passaria em todos os
    testes acima, porque eles só olham o atributo de cor."""
    from PySide6.QtGui import QColor

    theme.apply_theme(qapp, theme.Variant(mode="claro"))
    led.set_estado("ok")
    led.show()
    qapp.processEvents()

    img = led.grab().toImage()
    centro = QColor(img.pixelColor(led.width() // 2, led.height() // 2))
    assert centro.name().upper() == theme.OK.upper()
    led.close()
