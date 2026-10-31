"""Visualizador de modelo 3D — a parte testável sem contexto OpenGL (Fase 6).

Mesmo motivo do `test_hdri_viewer.py`: QOpenGLWidget não roda no modo
offscreen do pytest. O que dá pra cobrir aqui: o preparo do buffer de
vértices e a coerência entre o shader e a câmera já testada em
`test_orbit_camera.py`.
"""

import numpy as np
import pytest

from assetdeck.model3d.obj_parser import Mesh
from assetdeck.ui import model_viewer
from assetdeck.ui.orbit_camera import OrbitCamera


def test_mesh_to_buffer_intercala_posicao_normal_e_uv():
    mesh = Mesh(
        positions=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        normals=[(0.0, 0.0, 1.0), (0.0, 1.0, 0.0)],
        uvs=[(0.25, 0.5), (0.75, 1.0)],
    )
    buf = model_viewer._mesh_to_buffer(mesh)
    esperado = np.array(
        [1.0, 2.0, 3.0, 0.0, 0.0, 1.0, 0.25, 0.5,
         4.0, 5.0, 6.0, 0.0, 1.0, 0.0, 0.75, 1.0], dtype=np.float32,
    )
    assert np.array_equal(buf, esperado)


def test_mesh_to_buffer_e_float32():
    mesh = Mesh(positions=[(1.0, 2.0, 3.0)], normals=[(0.0, 0.0, 1.0)])
    assert model_viewer._mesh_to_buffer(mesh).dtype == np.float32


def test_shader_usa_normal_em_view_space():
    """A normal tem de ir pro fragment shader já em view-space (multiplicada
    por `normal_view` no vertex shader) — se isso saísse, a luz "presa na
    câmera" (headlight) giraria junto com o modelo em vez de ficar fixa."""
    assert "normal_view * normal" in model_viewer._VS


def test_shader_tem_luz_ambiente_minima():
    """A face oposta à câmera conserva pelo menos 38% da cor do material."""
    assert "0.38 + 0.62 * max(dot(n, vec3(0.0, 0.0, 1.0)), 0.0)" in model_viewer._FS


def test_fov_da_camera_bate_com_o_da_matriz_de_projecao():
    """`OrbitCamera.enquadrar` e a projeção perspectiva do shader usam o
    MESMO campo de visão (`TAN_MEIO_FOV`) — se saírem de sincronia, o
    modelo enquadrado ao carregar não cabe mais na tela depois do
    `perspective()` de verdade."""
    cam = OrbitCamera()
    cam.enquadrar(centro=(0.0, 0.0, 0.0), raio=1.0, tan_meio_fov=model_viewer.TAN_MEIO_FOV)
    assert cam.distancia == pytest.approx((1.0 / model_viewer.TAN_MEIO_FOV) * 1.3)


# ---- carregamento multiplataforma de OpenGL nativo ----

def test_gl_nativo_carrega_no_ambiente_atual():
    """No ambiente em execução, a biblioteca nativa e glDrawElements devem estar disponíveis."""
    assert model_viewer._gl_native is not None
    assert callable(model_viewer._gl_draw_elements)


def test_candidatos_gl_por_plataforma():
    """Valida que cada SO procura as bibliotecas nativas corretas."""
    candidatos_win = model_viewer._candidatos_gl_por_plataforma("win32")
    assert "opengl32" in candidatos_win

    candidatos_mac = model_viewer._candidatos_gl_por_plataforma("darwin")
    assert any("OpenGL" in c for c in candidatos_mac)

    candidatos_linux = model_viewer._candidatos_gl_por_plataforma("linux")
    assert "libGL.so.1" in candidatos_linux


def test_carregar_gl_nativo_com_falha_loga_e_retorna_none(monkeypatch, caplog):
    """Quando o carregamento falha, deve logar o erro com contexto e não lançar exceção."""
    import ctypes

    def _falha_cdll(_nome):
        raise OSError("Falha simulada de carregamento")

    monkeypatch.setattr(ctypes, "CDLL", _falha_cdll)
    with caplog.at_level("DEBUG"):
        lib, func = model_viewer._carregar_gl_nativo()
    assert lib is None
    assert func is None
    assert any("Falha simulada de carregamento" in record.message for record in caplog.records)

