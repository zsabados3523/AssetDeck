"""Janela dos visualizadores 3D (Fatia 90) — a parte testável sem OpenGL.

A janela em si não é instanciada aqui: ela monta dois `QOpenGLWidget`, que
não rodam no modo offscreen do pytest (mesma fronteira de
`test_hdri_viewer.py` e `test_model_viewer.py`). O que dá pra cobrir é o
que foi escrito justamente pra ser separável: a conta de onde a janela
nasce e a pintura dos cantos do palco.
"""

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QColor, QImage

from assetdeck.ui import theme
from assetdeck.ui.viewer_window import (
    RAIO_PALCO,
    _CantosDoPalco,
    posicao_centralizada,
)


# ---- abrir centralizada NO APLICATIVO (pedido do Rafael) ----

def test_centraliza_na_janela_do_app():
    app = QRect(100, 50, 1000, 800)
    pos = posicao_centralizada(app, QSize(400, 300))
    assert pos == QPoint(400, 300)  # 100 + (1000-400)/2, 50 + (800-300)/2


def test_centraliza_mesmo_com_sobra_impar():
    """Sobra ímpar não pode virar meio pixel nem estourar pra fora."""
    pos = posicao_centralizada(QRect(0, 0, 101, 101), QSize(50, 50))
    assert pos == QPoint(25, 25)


def test_nao_nasce_pra_fora_da_tela_quando_o_app_esta_no_canto():
    """A janela principal encostada na borda direita jogaria metade do
    visualizador pra fora do monitor — a área útil da tela segura."""
    tela = QRect(0, 0, 1920, 1080)
    app_no_canto = QRect(1500, 800, 420, 280)
    pos = posicao_centralizada(app_no_canto, QSize(1000, 660), tela)

    assert pos.x() + 1000 <= tela.width()
    assert pos.y() + 660 <= tela.height()
    assert pos.x() >= 0 and pos.y() >= 0


def test_app_menor_que_o_visualizador_ainda_fica_dentro_da_tela():
    tela = QRect(0, 0, 1280, 720)
    pos = posicao_centralizada(QRect(10, 10, 300, 200), QSize(1000, 660), tela)
    assert pos == QPoint(0, 0)


def test_sem_limite_a_posicao_nao_e_travada():
    """Sem área útil informada (nenhuma tela disponível) a função não
    inventa limite nenhum — só centraliza."""
    pos = posicao_centralizada(QRect(0, 0, 100, 100), QSize(400, 400))
    assert pos == QPoint(-150, -150)


# ---- cantos arredondados do palco ----

def _pintar_cantos(qapp, tam=120):
    """Desenha o widget de cantos sobre uma imagem de cor conhecida.

    Magenta como fundo: qualquer pixel que continuar magenta é pixel que o
    widget deixou passar (o miolo, onde o OpenGL aparece).
    """
    from PySide6.QtWidgets import QWidget

    hospedeiro = QWidget()
    hospedeiro.resize(tam, tam)
    cantos = _CantosDoPalco(hospedeiro)
    cantos.setGeometry(0, 0, tam, tam)

    img = QImage(tam, tam, QImage.Format.Format_ARGB32)
    img.fill(QColor("magenta"))
    cantos.render(img)
    return img


def test_o_canto_recebe_a_cor_de_fundo_da_janela(qapp):
    """O pixel (0,0) fica FORA do retângulo arredondado, então tem de ser
    tapado com o fundo do tema — é isso que arredonda a superfície de
    OpenGL, que ignora `border-radius` do QSS."""
    img = _pintar_cantos(qapp)
    fundo = QColor(theme.current_colors()["bg"])
    assert img.pixelColor(0, 0) == fundo
    assert img.pixelColor(0, 0) != QColor("magenta")


def test_o_miolo_continua_intocado(qapp):
    """Se o widget pintasse o meio, ele cobriria o render — foi exatamente
    esse o erro da sombra da Fatia 74 ("escurece tudo")."""
    img = _pintar_cantos(qapp)
    assert img.pixelColor(60, 60) == QColor("magenta")


def test_o_que_e_tapado_fica_restrito_ao_raio(qapp):
    """Um pixel logo depois do arco, na borda de cima, já é miolo. Segura
    o raio de crescer sem querer e comer a imagem."""
    img = _pintar_cantos(qapp)
    assert img.pixelColor(RAIO_PALCO + 6, 2) == QColor("magenta")
