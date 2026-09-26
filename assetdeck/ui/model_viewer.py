"""Visualizador de modelo 3D com OpenGL — Fase 6.

Começou como POC só de `.obj`; a Fatia 72 trouxe `.fbx` (via `assimp-py`,
lê a geometria direto) e `.blend` (via o próprio Blender headless, ver
`model3d/blend_loader.py` — não existe parser de terceiros confiável pro
formato binário fechado). `model3d/loader.py` escolhe o loader certo pela
extensão; este módulo só desenha o que qualquer um deles devolver.
UVs, cor e textura de cor base são renderizados quando disponíveis.

Mesmo padrão do visualizador de HDRI (Fatia 34/65):
- Parser/câmera (`model3d/obj_parser.py`, `ui/orbit_camera.py`) sem
  Qt/OpenGL, testáveis no pytest normal.
- Carregamento em thread (`QThreadPool`) — não trava a UI abrindo um
  modelo grande.
- Janela PRÓPRIA, não overlay embutido: um `QOpenGLWidget` em qualquer
  lugar da árvore de um top-level muda o modo de composição da JANELA
  INTEIRA na primeira aparição — dentro da `MainWindow` isso fazia o app
  inteiro "piscar" (revertido na Fatia 65 por causa disso no HDRI).

Desde a Fatia 90 a janela não mora mais aqui: é a `VisualizadorWindow`
(`ui/viewer_window.py`), a MESMA do HDRI, com as duas superfícies num
`QStackedWidget`. Este módulo ficou só com a superfície de render.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QMatrix4x4, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from assetdeck.model3d.loader import load_mesh
from assetdeck.model3d.obj_parser import MaterialRange, Mesh
from assetdeck.ui import pools
from assetdeck.ui.orbit_camera import OrbitCamera

log = logging.getLogger(__name__)

_GL_FLOAT = 0x1406
_GL_UNSIGNED_INT = 0x1405
_GL_TRIANGLES = 0x0004
_GL_DEPTH_TEST = 0x0B71
_GL_COLOR_BUFFER_BIT = 0x4000
_GL_DEPTH_BUFFER_BIT = 0x0100

_gl_native = ctypes.CDLL("libGL.so.1")
_gl_draw_elements = _gl_native.glDrawElements
_gl_draw_elements.argtypes = (ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
                              ctypes.c_void_p)
_gl_draw_elements.restype = None

TAN_MEIO_FOV = 0.6  # ~62° de campo de visão — combina com OrbitCamera.enquadrar

_COR_FUNDO = (0.05, 0.05, 0.06, 1.0)  # mesmo tom do visualizador de HDRI
_VS = """#version 330 core
layout(location = 0) in vec3 pos;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec2 uv;
uniform mat4 mvp;
uniform mat3 normal_view;
out vec3 v_normal;
out vec2 v_uv;
void main() {
    v_normal = normalize(normal_view * normal);
    v_uv = uv;
    gl_Position = mvp * vec4(pos, 1.0);
}
"""

# Luz "presa na câmera" (headlight): o modelo nunca fica com a face
# visível totalmente escura, não importa o ângulo da órbita — POC não
# precisa simular iluminação de verdade, só mostrar a geometria com
# volume reconhecível.
_FS = """#version 330 core
in vec3 v_normal;
in vec2 v_uv;
out vec4 frag;
uniform vec3 cor_base;
uniform sampler2D cor_textura;
uniform bool tem_textura;
void main() {
    vec3 n = normalize(v_normal);
    float luz = 0.38 + 0.62 * max(dot(n, vec3(0.0, 0.0, 1.0)), 0.0);
    vec4 base = tem_textura ? texture(cor_textura, v_uv) : vec4(cor_base, 1.0);
    frag = vec4(base.rgb * luz, base.a);
}
"""


def _mesh_to_buffer(mesh: Mesh) -> np.ndarray:
    """Posição + normal + UV intercaladas (x,y,z,nx,ny,nz,u,v) — o
    formato que o VBO único abaixo espera. Em malhas indexadas cada
    vértice compartilhado aparece uma vez neste buffer."""
    n = len(mesh.positions)
    buf = np.empty((n, 8), dtype=np.float32)
    buf[:, 0:3] = mesh.positions
    buf[:, 3:6] = mesh.normals
    buf[:, 6:8] = mesh.uvs if len(mesh.uvs) else (0.0, 0.0)
    return buf.reshape(-1)


def _load_texture_image(path: Path) -> QImage | None:
    image = QImage(str(path))
    if image.isNull():
        log.warning("Não consegui abrir a textura do modelo: %s", path)
        return None
    if max(image.width(), image.height()) > 2048:
        image = image.scaled(2048, 2048, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image


@dataclass
class PreparedModel:
    mesh: Mesh
    buffer: np.ndarray
    images: dict[Path, QImage | None]


class SinalCarga(QObject):
    """Emissor da carga em thread. Público porque quem escuta é a
    `VisualizadorWindow`, noutro módulo (Fatia 90)."""

    loaded = Signal(object)  # PreparedModel
    failed = Signal(str)


class _LoadJob(QRunnable):
    def __init__(self, sig: SinalCarga, path: Path, content_hash: str | None) -> None:
        super().__init__()
        self._sig = sig
        self._path = path
        self._content_hash = content_hash

    def run(self) -> None:
        try:
            mesh = load_mesh(self._path, self._content_hash)
            images = {path: _load_texture_image(path)
                      for path in {m.texture for m in mesh.materials if m.texture}}
            self._sig.loaded.emit(PreparedModel(mesh, _mesh_to_buffer(mesh), images))
        except Exception as exc:
            log.exception("Não consegui ler o modelo %s", self._path)
            self._sig.failed.emit(str(exc))


class ModelGLView(QOpenGLWidget):
    """A superfície de render. Arrastar orbita, a roda do mouse dá zoom."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.camera = OrbitCamera()
        self._bounds = None
        self._materials: list[MaterialRange] = []
        self._pendente: np.ndarray | None = None
        self._indices_pendente: np.ndarray | None = None
        self._n_vertices = 0
        self._n_indices = 0
        self._ultimo_pos = None
        self._gl = None
        self._textures: dict[Path, QOpenGLTexture | None] = {}
        self._pending_images: dict[Path, QImage | None] = {}
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_mesh(self, mesh: Mesh, *, buffer: np.ndarray | None = None,
                 images: dict[Path, QImage | None] | None = None) -> None:
        """O VBO só pode ser criado com o contexto GL corrente — igual ao
        HDRI, a malha fica pendente até o próximo `paintGL`."""
        self._bounds = mesh.bounds()
        self._materials = mesh.materials
        self._pendente = buffer if buffer is not None else _mesh_to_buffer(mesh)
        self._indices_pendente = mesh.indices
        self._pending_images = images or {}
        self._n_vertices = len(mesh.positions)
        self._n_indices = len(mesh.indices) if mesh.indices is not None else 0
        self.enquadrar()

    def enquadrar(self) -> None:
        """Recentraliza a câmera na malha carregada.

        Roda ao carregar e no botão "Enquadrar" da janela (Fatia 90) — a
        conta do centro e do raio vive AQUI e não nos dois lugares, senão
        um enquadramento acaba divergindo do outro."""
        if self._bounds is None:
            return
        canto_min, canto_max = self._bounds
        centro = tuple((lo + hi) / 2 for lo, hi in zip(canto_min, canto_max))
        raio = max(
            ((hi - lo) / 2 for lo, hi in zip(canto_min, canto_max)), default=1.0
        ) or 1.0
        self.camera.enquadrar(centro, raio, TAN_MEIO_FOV)
        self.update()

    # ---- OpenGL ----

    def initializeGL(self) -> None:  # noqa: N802
        self.context().aboutToBeDestroyed.connect(self._cleanup_textures)
        self._gl = QOpenGLFunctions_3_3_Core()
        self._gl.initializeOpenGLFunctions()
        self._gl.glEnable(_GL_DEPTH_TEST)

        self._prog = QOpenGLShaderProgram()
        ok_vs = self._prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VS)
        ok_fs = self._prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FS)
        ok_link = self._prog.link()
        if not (ok_vs and ok_fs and ok_link):
            raise RuntimeError(f"Shader do visualizador de modelo falhou: {self._prog.log()}")

        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vbo = QOpenGLBuffer()
        self._vbo.create()
        self._vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)
        self._ibo = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
        self._ibo.create()
        self._ibo.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)

    def paintGL(self) -> None:  # noqa: N802
        self._gl.glClearColor(*_COR_FUNDO)
        self._gl.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)

        if self._pendente is not None:
            for texture in self._textures.values():
                if texture is not None:
                    texture.destroy()
            self._textures.clear()
            dados = self._pendente
            self._vao.bind()
            self._vbo.bind()
            self._vbo.allocate(dados.tobytes(), dados.nbytes)
            stride = 8 * 4  # 8 floats por vértice, 4 bytes cada
            self._prog.enableAttributeArray(0)
            self._prog.setAttributeBuffer(0, _GL_FLOAT, 0, 3, stride)
            self._prog.enableAttributeArray(1)
            self._prog.setAttributeBuffer(1, _GL_FLOAT, 3 * 4, 3, stride)
            self._prog.enableAttributeArray(2)
            self._prog.setAttributeBuffer(2, _GL_FLOAT, 6 * 4, 2, stride)
            if not self._ibo.bind():
                raise RuntimeError("Não consegui ativar o buffer de índices do modelo")
            if self._indices_pendente is not None:
                indices = self._indices_pendente
                self._ibo.allocate(indices.tobytes(), indices.nbytes)
                self._indices_pendente = None
            self._vao.release()
            self._pendente = None

        if self._n_vertices == 0:
            return

        aspecto = max(self.width(), 1) / max(self.height(), 1)
        fov_graus = 2.0 * np.degrees(np.arctan(TAN_MEIO_FOV))
        projecao = QMatrix4x4()
        projecao.perspective(fov_graus, aspecto, 0.01, 10000.0)

        view = QMatrix4x4()
        view.lookAt(QVector3D(*self.camera.eye()), QVector3D(*self.camera.alvo),
                    QVector3D(0.0, 1.0, 0.0))

        mvp = projecao * view
        normal_view = view.normalMatrix()

        self._prog.bind()
        self._prog.setUniformValue("mvp", mvp)
        self._prog.setUniformValue("normal_view", normal_view)
        self._prog.setUniformValue1i("cor_textura", 0)
        self._vao.bind()
        ranges = self._materials or [
            MaterialRange(0, self._n_indices or self._n_vertices)]
        for material in ranges:
            self._prog.setUniformValue("cor_base", *material.color)
            texture = self._get_texture(material.texture) if material.texture else None
            self._prog.setUniformValue1i("tem_textura", int(texture is not None))
            if texture is not None:
                texture.bind(0)
            if self._n_indices:
                _gl_draw_elements(_GL_TRIANGLES, material.count, _GL_UNSIGNED_INT,
                                  ctypes.c_void_p(material.start * 4))
            else:
                self._gl.glDrawArrays(_GL_TRIANGLES, material.start, material.count)
            if texture is not None:
                texture.release(0)
        self._vao.release()
        self._prog.release()

    def _get_texture(self, path: Path) -> QOpenGLTexture | None:
        if path not in self._textures:
            image = (self._pending_images.pop(path) if path in self._pending_images
                     else _load_texture_image(path))
            if image is None:
                self._textures[path] = None
            else:
                texture = QOpenGLTexture(image.mirrored())
                texture.setMinMagFilters(QOpenGLTexture.Filter.LinearMipMapLinear,
                                         QOpenGLTexture.Filter.Linear)
                texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
                self._textures[path] = texture
        return self._textures[path]

    def _cleanup_textures(self) -> None:
        if not self._textures:
            self._pending_images.clear()
            return
        self.makeCurrent()
        for texture in self._textures.values():
            if texture is not None:
                texture.destroy()
        self._textures.clear()
        self._pending_images.clear()
        self.doneCurrent()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.context() is not None:
            self._cleanup_textures()
        super().closeEvent(event)

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

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.camera.zoom(event.angleDelta().y() / 120.0)
        self.update()


def iniciar_carga(sig: SinalCarga, path: Path,
                  content_hash: str | None = None) -> None:
    """Lê a geometria fora da thread da UI (um .blend passa pelo Blender
    headless e demora segundos).

    A JANELA mora em `ui/viewer_window.py` desde a Fatia 90 — este módulo
    ficou com o que é do modelo: shader, VBO, câmera e esta carga.
    """
    pools.interativo().start(_LoadJob(sig, path, content_hash))
