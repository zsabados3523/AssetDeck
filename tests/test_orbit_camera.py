"""Câmera do visualizador de modelo 3D (Fase 6 — POC).

Mesma separação da Fatia 34: a matemática mora fora do QOpenGLWidget de
propósito, pra o pytest conseguir cobrir sem contexto GL.
"""

import math

import pytest

from assetdeck.ui.orbit_camera import DISTANCIA_MIN, PITCH_MAX, OrbitCamera


def test_comeca_a_uma_distancia_do_alvo():
    cam = OrbitCamera()
    x, y, z = cam.eye()
    d = math.sqrt(x * x + y * y + z * z)
    assert d == pytest.approx(cam.distancia)


def test_arrastar_gira_ao_redor_do_alvo():
    cam = OrbitCamera(yaw=0.0, pitch=0.0)
    cam.drag(100, 0)
    assert cam.yaw == pytest.approx(360 - 30.0)  # 100px * 0.3°/px
    assert cam.pitch == 0.0


def test_pitch_trava_antes_dos_polos():
    cam = OrbitCamera()
    cam.drag(0, -1_000_000)
    assert cam.pitch == -PITCH_MAX
    cam.drag(0, 2_000_000)
    assert cam.pitch == PITCH_MAX


def test_yaw_da_a_volta_sem_acumular():
    cam = OrbitCamera()
    for _ in range(50):
        cam.drag(-360, 0)
    assert 0.0 <= cam.yaw < 360.0


def test_zoom_aproxima_e_afasta():
    cam = OrbitCamera(distancia=10.0)
    cam.zoom(1.0)  # roda "pra frente" — aproxima
    assert cam.distancia == pytest.approx(9.0)
    cam.zoom(-1.0)  # roda "pra trás" — afasta de volta
    assert cam.distancia == pytest.approx(10.0)


def test_zoom_nao_passa_do_minimo():
    cam = OrbitCamera(distancia=0.1)
    for _ in range(200):
        cam.zoom(5.0)
    assert cam.distancia == DISTANCIA_MIN


def test_eye_sempre_a_distancia_certa_do_alvo_em_qualquer_angulo():
    cam = OrbitCamera(alvo=(1.0, 2.0, 3.0), distancia=5.0, yaw=137.0, pitch=-41.0)
    ex, ey, ez = cam.eye()
    ax, ay, az = cam.alvo
    d = math.sqrt((ex - ax) ** 2 + (ey - ay) ** 2 + (ez - az) ** 2)
    assert d == pytest.approx(5.0)


def test_enquadrar_centraliza_e_ajusta_a_distancia():
    cam = OrbitCamera()
    cam.enquadrar(centro=(2.0, 0.0, 0.0), raio=1.0, tan_meio_fov=0.5)
    assert cam.alvo == (2.0, 0.0, 0.0)
    assert cam.distancia == pytest.approx((1.0 / 0.5) * 1.3)


def test_enquadrar_nao_deixa_distancia_negativa_com_raio_zero():
    """Modelo degenerado (um vértice só, bounding box de raio 0) não pode
    aproximar a câmera até dentro do objeto."""
    cam = OrbitCamera()
    cam.enquadrar(centro=(0.0, 0.0, 0.0), raio=0.0)
    assert cam.distancia >= DISTANCIA_MIN
