"""Visualizador de HDRI/EXR com OpenGL (Fatia 34).

Duplo clique num .hdr/.exr abre aqui em vez do PreviewPopup: a imagem
equirretangular achatada não deixa avaliar como a luz envolve o ambiente
nem como ela reflete.

Dois modos, ambos resolvidos SÓ no fragment shader sobre um triângulo de
tela cheia — sem malha de esfera, sem índices, sem biblioteca de geometria:

- Ambiente: monta a direção do raio por pixel e amostra o equirretangular.
  É "estar dentro" do HDRI.
- Esfera: interseção raio×esfera, reflete e amostra a mesma textura. Fora
  da esfera continua mostrando o ambiente, então a bola aparece flutuando
  dentro da cena.

O carregamento (0,76s num 4K) vai para thread, senão a janela congela ao
abrir — mesmo padrão do PreviewPopup.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QSurfaceFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from assetdeck.thumbs.hdr import load_tonemapped
from assetdeck.ui.hdri_camera import HdriCamera

log = logging.getLogger(__name__)

MODO_AMBIENTE = 0
MODO_ESFERA = 1

_GL_FLOAT = 0x1406
_GL_TRIANGLES = 0x0004
_GL_COLOR_BUFFER_BIT = 0x4000

# Um triângulo que cobre a tela inteira (mais barato que dois do quad).
_VERTICES = np.array([-1.0, -1.0, 3.0, -1.0, -1.0, 3.0], dtype=np.float32)

_VS = """#version 330 core
layout(location = 0) in vec2 pos;
out vec2 ndc;
void main() {
    ndc = pos;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

# A projeção equirretangular aqui é a MESMA de hdri_camera.direction_to_equirect
# (testada em Python) — se uma mudar, a outra tem de mudar junto.
_FS = """#version 330 core
in vec2 ndc;
out vec4 frag;

uniform sampler2D env;
uniform vec3 cam_right;
uniform vec3 cam_up;
uniform vec3 cam_fwd;
uniform float aspect;
uniform float tan_half_fov;
uniform int modo;

const float PI = 3.14159265359;

vec2 dir_to_equirect(vec3 d) {
    d = normalize(d);
    float u = 0.5 + atan(d.x, -d.z) / (2.0 * PI);
    float v = 0.5 - asin(clamp(d.y, -1.0, 1.0)) / PI;
    return vec2(u, v);
}

vec3 amostrar(vec3 d) {
    return texture(env, dir_to_equirect(d)).rgb;
}

void main() {
    vec3 dir = normalize(cam_fwd
                         + cam_right * ndc.x * aspect * tan_half_fov
                         + cam_up * ndc.y * tan_half_fov);

    if (modo == 1) {
        // A esfera acompanha a câmera (sempre à frente dela), em vez de
        // ficar presa a um ponto do mundo: assim girar a vista roda o
        // AMBIENTE em volta da bola — que é como se avalia um reflexo.
        // Fixa no mundo, ela escapava da tela ao girar.
        vec3 centro = cam_fwd * 3.0;
        float raio = 1.0;
        vec3 oc = -centro;
        float b = dot(oc, dir);
        float c = dot(oc, oc) - raio * raio;
        float disc = b * b - c;
        if (disc > 0.0) {
            float t = -b - sqrt(disc);
            if (t > 0.0) {
                vec3 p = dir * t;
                vec3 n = normalize(p - centro);
                // Reflete o ambiente: é assim que se avalia um HDRI.
                frag = vec4(amostrar(reflect(dir, n)), 1.0);
                return;
            }
        }
    }
    frag = vec4(amostrar(dir), 1.0);
}
"""


def image_to_qimage(img) -> QImage:
    """PIL RGB → QImage RGBA8888 dono dos próprios bytes.

    Separado do widget de propósito: é a parte do caminho da textura que
    o pytest consegue cobrir sem contexto OpenGL.
    """
    rgba = img.convert("RGBA")
    dados = rgba.tobytes("raw", "RGBA")
    return QImage(dados, rgba.width, rgba.height,
                  QImage.Format.Format_RGBA8888).copy()


class _Signaller(QObject):
    loaded = Signal(QImage)
    failed = Signal(str)


class _LoadJob(QRunnable):
    """Carrega e tonemapa fora da thread da UI (0,76s num HDRI 4K)."""

    def __init__(self, sig: _Signaller, path: Path) -> None:
        super().__init__()
        self._sig = sig
        self._path = path

    def run(self) -> None:
        try:
            self._sig.loaded.emit(image_to_qimage(load_tonemapped(self._path)))
        except Exception as exc:
            log.exception("Não consegui carregar o HDRI %s", self._path)
            self._sig.failed.emit(str(exc))


class HdriGLView(QOpenGLWidget):
    """A superfície de render. Arrastar gira a vista."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.camera = HdriCamera()
        self.modo = MODO_AMBIENTE
        self.tan_half_fov = 1.0  # ~90° de campo de visão
        self._imagem: QImage | None = None
        self._textura: QOpenGLTexture | None = None
        self._pendente: QImage | None = None
        self._ultimo_pos = None
        self._gl = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_image(self, img: QImage) -> None:
        """A textura só pode ser criada com o contexto GL corrente, e a
        imagem costuma chegar da thread antes do primeiro paint — por isso
        fica pendente até o initializeGL/paintGL acontecer."""
        self._imagem = img
        self._pendente = img
        self.update()

    def set_modo(self, modo: int) -> None:
        self.modo = modo
        self.update()

    # ---- OpenGL ----

    def initializeGL(self) -> None:  # noqa: N802
        self._gl = QOpenGLFunctions_3_3_Core()
        self._gl.initializeOpenGLFunctions()

        self._prog = QOpenGLShaderProgram()
        ok_vs = self._prog.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, _VS)
        ok_fs = self._prog.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, _FS)
        ok_link = self._prog.link()
        if not (ok_vs and ok_fs and ok_link):
            # Sem shader não há o que desenhar; falhar alto (o log do Qt
            # traz a linha exata do erro de GLSL).
            raise RuntimeError(f"Shader do visualizador falhou: {self._prog.log()}")

        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vao.bind()
        self._vbo = QOpenGLBuffer()
        self._vbo.create()
        self._vbo.bind()
        self._vbo.allocate(_VERTICES.tobytes(), _VERTICES.nbytes)
        self._prog.enableAttributeArray(0)
        self._prog.setAttributeBuffer(0, _GL_FLOAT, 0, 2)
        self._vao.release()

    def paintGL(self) -> None:  # noqa: N802
        self._gl.glClearColor(0.05, 0.05, 0.06, 1.0)
        self._gl.glClear(_GL_COLOR_BUFFER_BIT)

        if self._pendente is not None:
            if self._textura is not None:
                self._textura.destroy()
            # SEM mirrored(): o Qt envia a scanline 0 (topo do QImage) como
            # primeira linha da textura, então v=0 já é o topo — que é o que
            # a projeção espera. Espelhar aqui virava a cena de cabeça pra
            # baixo (a rua ia parar no céu).
            self._textura = QOpenGLTexture(self._pendente)
            self._textura.setWrapMode(QOpenGLTexture.CoordinateDirection.DirectionS,
                                      QOpenGLTexture.WrapMode.Repeat)
            self._textura.setWrapMode(QOpenGLTexture.CoordinateDirection.DirectionT,
                                      QOpenGLTexture.WrapMode.ClampToEdge)
            self._textura.setMinMagFilters(QOpenGLTexture.Filter.Linear,
                                           QOpenGLTexture.Filter.Linear)
            self._pendente = None

        if self._textura is None:
            return

        direita, cima, frente = self.camera.basis()
        self._prog.bind()
        self._textura.bind(0)
        self._prog.setUniformValue1i("env", 0)
        self._prog.setUniformValue("cam_right", *direita)
        self._prog.setUniformValue("cam_up", *cima)
        self._prog.setUniformValue("cam_fwd", *frente)
        self._prog.setUniformValue1f("aspect", max(self.width(), 1) / max(self.height(), 1))
        self._prog.setUniformValue1f("tan_half_fov", self.tan_half_fov)
        self._prog.setUniformValue1i("modo", self.modo)
        self._vao.bind()
        self._gl.glDrawArrays(_GL_TRIANGLES, 0, 3)
        self._vao.release()
        self._prog.release()

    def resizeGL(self, w: int, h: int) -> None:  # noqa: N802
        self._gl.glViewport(0, 0, w, h)

    # ---- interação ----

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._ultimo_pos = event.position()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._ultimo_pos is None:
            return
        p = event.position()
        self.camera.drag(p.x() - self._ultimo_pos.x(), p.y() - self._ultimo_pos.y())
        self._ultimo_pos = p
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._ultimo_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.camera.reset()
        self.update()

    # ---- limpeza ----

    def cleanup(self) -> None:
        """Recursos de GL só podem ser liberados com o contexto corrente —
        deixar o Qt coletar depois gera 'destroy() called without a current
        context' e vaza a textura (um HDRI 4K são 32MB na GPU)."""
        if self._textura is None:
            return
        self.makeCurrent()
        try:
            self._textura.destroy()
            self._textura = None
        finally:
            self.doneCurrent()


class HdriViewer(QDialog):
    """Janela própria — superfície GL + alternador de modo.

    Fatia 65 tinha tentado virar `OverlayPanel` (embutido na janela
    principal, como o `PreviewPopup`) — revertido no mesmo dia: Rafael
    relatou que o "piscar" piorou, o APP INTEIRO parecia fechar e abrir,
    não só uma janelinha pequena. Causa real (achada revisando depois do
    relato): um `QOpenGLWidget` em QUALQUER lugar da árvore de widgets de
    um top-level muda o modo de composição da JANELA INTEIRA daquele
    top-level (Qt reflui todo o conteúdo por uma textura em vez do caminho
    raster normal) — isso só acontece na primeira vez que aparece na tela.
    Com o GL dentro da MainWindow, era a janela inteira do AssetDeck que
    sofria essa transição; como janela PRÓPRIA (aqui), só ela.
    `PreviewPopup` continua `OverlayPanel` — não usa OpenGL, não tem esse
    problema."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(1000, 620)

        self.view = HdriGLView()
        self.status = QLabel("Carregando…")

        self.btn_ambiente = QPushButton("Ambiente")
        self.btn_esfera = QPushButton("Esfera de reflexo")
        self._grupo = QButtonGroup(self)
        for i, b in ((MODO_AMBIENTE, self.btn_ambiente), (MODO_ESFERA, self.btn_esfera)):
            b.setCheckable(True)
            self._grupo.addButton(b, i)
            b.clicked.connect(lambda _c=False, m=i: self.view.set_modo(m))
        self.btn_ambiente.setChecked(True)

        topo = QHBoxLayout()
        topo.addWidget(self.btn_ambiente)
        topo.addWidget(self.btn_esfera)
        topo.addStretch()
        topo.addWidget(self.status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(topo)
        layout.addWidget(self.view, stretch=1)

        self._sig = _Signaller()
        self._sig.loaded.connect(self._on_loaded)
        self._sig.failed.connect(self._on_failed)

    def show_for(self, path: Path) -> None:
        self.setWindowTitle(f"HDRI — {path.name}")
        self.status.setText("Carregando…")
        self.view.camera.reset()
        self.show()
        self.raise_()
        QThreadPool.globalInstance().start(_LoadJob(self._sig, path))

    def _on_loaded(self, img: QImage) -> None:
        self.view.set_image(img)
        self.status.setText(
            f"{img.width()}×{img.height()}  ·  arraste para girar, duplo clique centraliza")

    def _on_failed(self, msg: str) -> None:
        self.status.setText(f"Falhou: {msg}")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.view.cleanup()  # libera a textura na GPU (32MB num HDRI 4K)
        super().closeEvent(event)


def ensure_gl_format() -> None:
    """Pede OpenGL 3.3 Core ANTES de qualquer widget existir. Sem isto o Qt
    entrega um contexto de compatibilidade antigo e o shader #version 330
    não compila."""
    fmt = QSurfaceFormat.defaultFormat()
    if fmt.majorVersion() < 3 or (fmt.majorVersion() == 3 and fmt.minorVersion() < 3):
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        QSurfaceFormat.setDefaultFormat(fmt)
