"""Preview ampliado: tamanho padronizado do cartão, Esc/clique no fundo
fecham (Fatia 65: overlay embutido, não janela separada — clicar no
CARTÃO não pode fechar, só o fundo em volta)."""

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QWidget

from assetdeck.ui.preview_popup import PreviewPopup


@pytest.fixture
def popup(qapp):
    # Host grande o bastante pra travar no teto de 1100×800 (mesmo teto de
    # antes, quando vinha da tela inteira) — deixa os números previsíveis.
    host = QWidget()
    host.resize(1600, 1200)
    host.show()  # isVisible() de um widget filho depende do ancestral mostrado
    p = PreviewPopup(host)
    p._resize_card()
    yield p
    p.close()
    host.close()
    host.deleteLater()


def test_cartao_tem_tamanho_padronizado(popup):
    assert popup._card.width() == popup._win_w == 1100
    assert popup._card.height() == popup._win_h == 800


def test_imagem_gigante_e_reduzida_para_caber(popup):
    fitted = popup._fit(QPixmap(8192, 8192))

    assert fitted.width() <= popup._win_w
    assert fitted.height() <= popup._win_h
    assert fitted.width() == fitted.height()  # proporção mantida


def test_imagem_pequena_nao_e_ampliada(popup):
    fitted = popup._fit(QPixmap(120, 90))

    assert (fitted.width(), fitted.height()) == (120, 90)


def test_cartao_nao_muda_de_tamanho_entre_imagens(popup):
    """O incômodo do Rafael: popup gigante para uns assets, minúsculo para
    outros. O tamanho do CARTÃO é o mesmo, seja qual for a imagem."""
    antes = (popup._card.width(), popup._card.height())

    popup._fit(QPixmap(8192, 4096))
    popup._fit(QPixmap(64, 64))

    assert (popup._card.width(), popup._card.height()) == antes


def test_proporcao_preservada_em_imagem_panoramica(popup):
    fitted = popup._fit(QPixmap(4096, 2048))  # 2:1 (HDRI)
    assert fitted.width() == fitted.height() * 2


def test_open_overlay_mostra_close_overlay_esconde(popup):
    assert not popup.isVisible()

    popup.open_overlay()
    assert popup.isVisible()

    popup.close_overlay()
    assert not popup.isVisible()


def test_esc_fecha(popup):
    """Pedido de sempre: Esc fecha o preview."""
    popup.open_overlay()

    evento = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    popup.keyPressEvent(evento)

    assert not popup.isVisible()


def test_clique_no_fundo_fecha(popup):
    """Fatia 65: clicar fora do cartão (no fundo escurecido) fecha — o
    equivalente embutido do "clicar de volta no app fechava o popup" de
    quando era janela separada."""
    popup.open_overlay()

    evento = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(5, 5), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    popup.mousePressEvent(evento)

    assert not popup.isVisible()


def test_fit_to_host_acompanha_o_tamanho_do_host(popup):
    """O overlay tem de continuar cobrindo o host inteiro se a janela do
    AssetDeck for redimensionada com o preview aberto. `_fit_to_host()` é o
    mesmo método que o `eventFilter` chama sozinho a cada `QResizeEvent`
    real do host — testado direto aqui pra não depender da fiação de
    eventos de verdade do Qt (frágil de reproduzir num widget órfão de
    teste, sem afetar a garantia: `eventFilter` só decide QUANDO chamar,
    a lógica de tamanho é toda daqui)."""
    popup.open_overlay()

    popup._host.resize(1000, 700)
    popup._fit_to_host()

    assert (popup.width(), popup.height()) == (1000, 700)
