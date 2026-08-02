"""Estado da câmera do visualizador de HDRI (Fatia 34).

Sem nenhum Qt e sem OpenGL de propósito: é aqui que mora a lógica de
verdade (para onde a vista aponta, o que o arrasto faz, onde ela trava), e
assim ela roda no pytest normal. O `QOpenGLWidget` não funciona no modo
offscreen dos testes — separar as duas coisas é o que impede a fatia
inteira de ficar sem cobertura.
"""

from __future__ import annotations

import math

# Quanto a vista gira por pixel arrastado. 0.25°/px dá uma volta completa
# em ~1440px — perto de uma tela de largura, que é o esperado ao arrastar.
GRAUS_POR_PIXEL = 0.25

# O pitch trava um pouco antes dos polos: exatamente em ±90° a direção
# "para cima" da câmera fica indefinida e a vista dá um salto.
PITCH_MAX = 89.0


class HdriCamera:
    """Para onde a câmera olha dentro do HDRI. Ângulos em GRAUS."""

    def __init__(self, yaw: float = 0.0, pitch: float = 0.0) -> None:
        self.yaw = yaw
        self.pitch = pitch

    def drag(self, dx: float, dy: float) -> None:
        """Arrasto do mouse em pixels. Arrastar para a direita traz o que
        está à direita para o centro — o mesmo sentido de arrastar um mapa."""
        self.yaw = _wrap(self.yaw - dx * GRAUS_POR_PIXEL)
        self.pitch = _clamp(self.pitch - dy * GRAUS_POR_PIXEL, -PITCH_MAX, PITCH_MAX)

    def reset(self) -> None:
        self.yaw = 0.0
        self.pitch = 0.0

    def basis(self) -> tuple[tuple[float, float, float], ...]:
        """Base ortonormal (direita, cima, frente) da câmera, em coordenadas
        de mundo. O shader monta a direção de cada raio a partir dela."""
        y = math.radians(self.yaw)
        p = math.radians(self.pitch)
        cy, sy = math.cos(y), math.sin(y)
        cp, sp = math.cos(p), math.sin(p)
        frente = (sy * cp, sp, -cy * cp)
        direita = (cy, 0.0, sy)
        cima = (-sy * sp, cp, cy * sp)
        return direita, cima, frente

    def forward(self) -> tuple[float, float, float]:
        return self.basis()[2]


def _wrap(graus: float) -> float:
    """Yaw dá a volta: 370° é 10°, e girar sem parar nunca acumula erro."""
    return graus % 360.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def direction_to_equirect(d: tuple[float, float, float]) -> tuple[float, float]:
    """Direção 3D → coordenada (u, v) na imagem equirretangular, ambos 0..1.

    Mesma convenção do shader; existe em Python para o teste poder provar
    que a projeção fecha (ida e volta) sem depender de contexto OpenGL.
    """
    x, y, z = d
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    u = 0.5 + math.atan2(x, -z) / (2.0 * math.pi)
    v = 0.5 - math.asin(max(-1.0, min(1.0, y))) / math.pi
    return u % 1.0, v
