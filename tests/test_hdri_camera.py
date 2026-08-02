"""Câmera do visualizador de HDRI (Fatia 34).

Esta é a camada que o pytest CONSEGUE cobrir: o QOpenGLWidget não roda
offscreen, então a matemática mora fora dele de propósito.
"""

import math

import pytest

from assetdeck.ui.hdri_camera import (
    PITCH_MAX,
    HdriCamera,
    direction_to_equirect,
)


def test_comeca_olhando_pra_frente():
    cam = HdriCamera()
    x, y, z = cam.forward()
    assert (round(x, 6), round(y, 6), round(z, 6)) == (0.0, 0.0, -1.0)


def test_arrastar_pra_direita_gira_a_vista():
    cam = HdriCamera()
    cam.drag(100, 0)
    assert cam.yaw == pytest.approx(360 - 25.0)  # 100px * 0.25°/px
    assert cam.pitch == 0.0


def test_arrastar_pra_cima_leva_a_imagem_pra_cima():
    """Sentido conferido pelo Rafael na tela: o eixo vertical estava
    invertido na primeira versão. Arrastar para cima (dy negativo) puxa o
    céu para perto, ou seja, a câmera baixa."""
    cam = HdriCamera()
    cam.drag(0, -40)
    assert cam.pitch == pytest.approx(-10.0)
    cam.drag(0, 80)
    assert cam.pitch == pytest.approx(10.0)


def test_pitch_trava_antes_dos_polos():
    """Exatamente em ±90° o 'para cima' da câmera fica indefinido e a
    vista dá um salto."""
    cam = HdriCamera()
    cam.drag(0, -100000)
    assert cam.pitch == -PITCH_MAX
    cam.drag(0, 200000)
    assert cam.pitch == PITCH_MAX


def test_yaw_da_a_volta_sem_acumular():
    cam = HdriCamera()
    for _ in range(20):
        cam.drag(-360, 0)  # 90° por vez
    assert 0.0 <= cam.yaw < 360.0


def test_girar_360_graus_volta_ao_mesmo_lugar():
    cam = HdriCamera()
    inicial = cam.forward()
    cam.drag(-1440, 0)  # 1440px * 0.25 = 360°
    for a, b in zip(cam.forward(), inicial):
        assert a == pytest.approx(b, abs=1e-9)


def test_base_e_ortonormal():
    """Se a base deixar de ser ortonormal, a imagem sai cisalhada."""
    cam = HdriCamera()
    cam.drag(137, -61)  # ângulo qualquer, nada redondo
    direita, cima, frente = cam.basis()

    for v in (direita, cima, frente):
        assert math.sqrt(sum(c * c for c in v)) == pytest.approx(1.0)
    assert sum(a * b for a, b in zip(direita, cima)) == pytest.approx(0.0, abs=1e-9)
    assert sum(a * b for a, b in zip(direita, frente)) == pytest.approx(0.0, abs=1e-9)
    assert sum(a * b for a, b in zip(cima, frente)) == pytest.approx(0.0, abs=1e-9)


def test_reset_volta_ao_inicio():
    cam = HdriCamera()
    cam.drag(500, 200)
    cam.reset()
    assert (cam.yaw, cam.pitch) == (0.0, 0.0)


# ---- projeção equirretangular (mesma convenção do shader) ----

def test_frente_cai_no_centro_da_imagem():
    u, v = direction_to_equirect((0, 0, -1))
    assert u == pytest.approx(0.5)
    assert v == pytest.approx(0.5)


def test_polos_vao_pro_topo_e_pra_base():
    assert direction_to_equirect((0, 1, 0))[1] == pytest.approx(0.0)
    assert direction_to_equirect((0, -1, 0))[1] == pytest.approx(1.0)


def test_a_emenda_360_fecha():
    """A costura da imagem: um passo antes e um depois têm de ser vizinhos,
    senão aparece uma linha vertical no meio da vista."""
    eps = 1e-4
    esquerda = direction_to_equirect((-eps, 0, 1))[0]
    direita = direction_to_equirect((eps, 0, 1))[0]
    assert esquerda > 0.999 or esquerda < 0.001
    assert direita < 0.001 or direita > 0.999


def test_projecao_e_estavel_com_vetor_nao_normalizado():
    perto = direction_to_equirect((0, 0, -1))
    longe = direction_to_equirect((0, 0, -500))
    assert perto == pytest.approx(longe)


@pytest.mark.parametrize("yaw", [0, 45, 90, 180, 270, 359])
def test_a_direcao_da_camera_percorre_a_imagem_toda(yaw):
    """Girar a câmera tem de varrer a largura da imagem — se u travasse,
    a vista não giraria."""
    cam = HdriCamera(yaw=yaw)
    u, v = direction_to_equirect(cam.forward())
    assert 0.0 <= u <= 1.0
    assert v == pytest.approx(0.5)  # pitch 0 = linha do horizonte
