"""Popup de preview: tamanho padronizado e fechar ao perder foco."""

import pytest
from PySide6.QtGui import QPixmap

from assetdeck.ui.preview_popup import PreviewPopup


@pytest.fixture
def popup(qapp):
    p = PreviewPopup()
    yield p
    p.close()


def test_janela_tem_tamanho_padronizado(popup):
    assert popup.width() == popup._win_w
    assert popup.height() == popup._win_h


def test_imagem_gigante_e_reduzida_para_caber(popup):
    fitted = popup._fit(QPixmap(8192, 8192))

    assert fitted.width() <= popup._win_w
    assert fitted.height() <= popup._win_h
    assert fitted.width() == fitted.height()  # proporção mantida


def test_imagem_pequena_nao_e_ampliada(popup):
    fitted = popup._fit(QPixmap(120, 90))

    assert (fitted.width(), fitted.height()) == (120, 90)


def test_janela_nao_muda_de_tamanho_entre_imagens(popup):
    """O incômodo do Rafael: popup gigante para uns assets, minúsculo para
    outros. Agora o tamanho é o mesmo, seja qual for a imagem."""
    antes = (popup.width(), popup.height())

    popup._fit(QPixmap(8192, 4096))
    popup._fit(QPixmap(64, 64))

    assert (popup.width(), popup.height()) == antes


def test_proporcao_preservada_em_imagem_panoramica(popup):
    fitted = popup._fit(QPixmap(4096, 2048))  # 2:1 (HDRI)
    assert fitted.width() == fitted.height() * 2


def test_nao_fecha_antes_de_receber_foco(popup):
    """Blindagem: um WM lento não pode fechar o popup assim que ele abre."""
    from PySide6.QtCore import QEvent

    popup.show()
    popup._was_active = False           # ainda não recebeu foco

    popup.changeEvent(QEvent(QEvent.Type.ActivationChange))

    assert popup.isVisible()            # continua aberto


def test_fecha_ao_perder_foco_depois_de_ativo(popup):
    """Pedido do Rafael: clicar de volta no app fecha o preview."""
    from PySide6.QtCore import QEvent

    popup.show()
    popup._was_active = True            # já esteve em foco

    popup.changeEvent(QEvent(QEvent.Type.ActivationChange))

    assert not popup.isVisible()
