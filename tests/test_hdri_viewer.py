"""Visualizador de HDRI — a parte testável sem contexto OpenGL (Fatia 34).

O QOpenGLWidget NÃO funciona no modo offscreen em que o pytest roda
("QOpenGLWidget is not supported on this platform"), então o render em si
é verificado à mão com DISPLAY=:0 (ver TODO.md). O que dá para cobrir
aqui: preparo da textura, o roteiro de qual janela abre, e o shader ser
coerente com a matemática já testada em test_hdri_camera.py.
"""

import numpy as np
import pytest
from PIL import Image
from PySide6.QtGui import QImage

from assetdeck.thumbs.hdr import can_hdr
from assetdeck.ui import hdri_viewer


# ---- preparo da textura ----

def test_imagem_vira_qimage_com_tamanho_e_formato_certos(qapp):
    img = Image.new("RGB", (8, 4), (255, 0, 0))
    q = hdri_viewer.image_to_qimage(img)

    assert (q.width(), q.height()) == (8, 4)
    assert q.format() == QImage.Format.Format_RGBA8888


def test_qimage_preserva_as_cores_e_a_orientacao(qapp):
    """A linha 0 do QImage vira a primeira linha da textura; se isso
    inverter, a cena aparece de cabeça para baixo (aconteceu de verdade
    durante a fatia, por causa de um mirrored() indevido)."""
    arr = np.zeros((4, 4, 3), np.uint8)
    arr[0, :] = (255, 0, 0)    # topo vermelho
    arr[-1, :] = (0, 0, 255)   # base azul
    q = hdri_viewer.image_to_qimage(Image.fromarray(arr, "RGB"))

    assert q.pixelColor(2, 0).name() == "#ff0000"
    assert q.pixelColor(2, 3).name() == "#0000ff"


def test_qimage_e_dono_dos_proprios_bytes(qapp):
    """QImage sobre buffer temporário vira lixo silencioso quando o buffer
    é coletado — o .copy() dentro da função é o que evita isso."""
    q = hdri_viewer.image_to_qimage(Image.new("RGB", (4, 4), (0, 255, 0)))
    import gc

    gc.collect()
    assert q.pixelColor(1, 1).name() == "#00ff00"


# ---- roteamento: qual janela abre ----

@pytest.mark.parametrize("nome", ["ceu.hdr", "estudio.exr", "CEU.HDR"])
def test_hdri_vai_para_o_visualizador(nome, tmp_path):
    assert can_hdr(tmp_path / nome) is True


@pytest.mark.parametrize("nome", ["textura.jpg", "modelo.blend", "mapa.png"])
def test_o_resto_continua_no_preview_de_sempre(nome, tmp_path):
    assert can_hdr(tmp_path / nome) is False


# ---- coerência entre o shader e a matemática testada ----

def test_o_shader_usa_a_mesma_projecao_da_camera():
    """A projeção existe duas vezes (GLSL e Python). O Python é testado em
    test_hdri_camera.py; aqui trava que o GLSL não saiu de sincronia."""
    fs = hdri_viewer._FS
    assert "atan(d.x, -d.z)" in fs      # mesma orientação de yaw
    assert "asin(clamp(d.y" in fs       # mesma orientação de pitch
    assert "0.5 - asin" in fs           # v=0 no topo, como o Python


def test_os_dois_modos_existem_e_sao_distintos():
    assert hdri_viewer.MODO_AMBIENTE != hdri_viewer.MODO_ESFERA
    assert "reflect(dir, n)" in hdri_viewer._FS  # a esfera reflete de verdade


def test_a_esfera_acompanha_a_camera():
    """Presa a um ponto do mundo (`vec3(0,0,-3)`), ela escapava da tela ao
    girar a vista — visto na tela durante a fatia. Tem de ficar centrada
    para o ambiente girar EM VOLTA dela."""
    assert "cam_fwd * 3.0" in hdri_viewer._FS
    assert "vec3(0.0, 0.0, -3.0)" not in hdri_viewer._FS


def test_triangulo_de_tela_cheia_cobre_o_viewport():
    """Um triângulo grande em vez de dois: se os vértices encolherem,
    sobra fundo sem pintar nos cantos."""
    v = hdri_viewer._VERTICES.reshape(-1, 2)
    assert len(v) == 3
    assert v.min() <= -1.0 and v.max() >= 3.0


def test_formato_gl_pedido_e_33_core(qapp):
    from PySide6.QtGui import QSurfaceFormat

    hdri_viewer.ensure_gl_format()
    fmt = QSurfaceFormat.defaultFormat()
    assert (fmt.majorVersion(), fmt.minorVersion()) >= (3, 3)
