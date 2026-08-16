"""Estado da câmera do visualizador de modelo 3D (Fase 6 — POC).

Mesma separação da Fatia 34 (`hdri_camera.py`): sem Qt/OpenGL, roda no
pytest normal. Órbita ao redor de um ALVO (não "olhar de dentro" como o
HDRI) — a câmera fica numa esfera de raio `distancia` centrada no alvo,
sempre olhando pra ele.
"""

from __future__ import annotations

import math

GRAUS_POR_PIXEL = 0.3
PITCH_MAX = 89.0
DISTANCIA_MIN = 0.05


class OrbitCamera:
    def __init__(self, alvo: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 distancia: float = 3.0, yaw: float = 35.0, pitch: float = 20.0) -> None:
        self.alvo = alvo
        self.distancia = distancia
        self.yaw = yaw
        self.pitch = pitch

    def drag(self, dx: float, dy: float) -> None:
        """Arrasto do mouse em pixels — mesmo sentido do `HdriCamera`:
        arrastar pra cima "puxa" o modelo pra cima."""
        self.yaw = _wrap(self.yaw - dx * GRAUS_POR_PIXEL)
        self.pitch = _clamp(self.pitch + dy * GRAUS_POR_PIXEL, -PITCH_MAX, PITCH_MAX)

    def zoom(self, passos: float) -> None:
        """Roda do mouse. Multiplicativo (não aditivo): cada passo
        aproxima/afasta a MESMA fração da distância atual, então o zoom
        não fica absurdamente rápido perto do modelo nem lento demais
        longe dele."""
        fator = 0.9 ** passos
        self.distancia = max(DISTANCIA_MIN, self.distancia * fator)

    def eye(self) -> tuple[float, float, float]:
        """Posição da câmera no mundo (coordenadas esféricas ao redor do alvo)."""
        y = math.radians(self.yaw)
        p = math.radians(self.pitch)
        cy, sy = math.cos(y), math.sin(y)
        cp, sp = math.cos(p), math.sin(p)
        return (
            self.alvo[0] + self.distancia * cp * sy,
            self.alvo[1] + self.distancia * sp,
            self.alvo[2] + self.distancia * cp * cy,
        )

    def enquadrar(self, centro: tuple[float, float, float], raio: float,
                  tan_meio_fov: float = 0.6) -> None:
        """Centraliza o alvo no modelo e ajusta a distância pra ele caber
        inteiro na tela — chamado uma vez ao carregar, sem o Rafael
        precisar dar zoom/pan na mão pra achar o objeto que acabou de
        abrir. `tan_meio_fov` tem que bater com o FOV usado no render
        (ver `ModelGLView`); a margem de 1.3× sobra espaço em volta, o
        modelo não encosta na borda da janela."""
        self.alvo = centro
        self.distancia = max(DISTANCIA_MIN, (raio / tan_meio_fov) * 1.3)


def _wrap(graus: float) -> float:
    return graus % 360.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
