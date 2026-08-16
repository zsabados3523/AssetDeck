"""Parser de `.obj` — só geometria (v/vn/f), sem MTL, sem UV, sem grupos.

Escopo de propósito (POC da Fase 6, plano fechado com o Rafael): provar
que dá pra ler e desenhar um modelo com câmera orbitando, não abrir o
formato inteiro. `.obj` foi a escolha porque é texto simples e aberto —
sem precisar de biblioteca de terceiros pra um parser deste tamanho.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mesh:
    """Um vértice por CANTO de triângulo usado (não deduplicado) — é o
    formato que `glDrawArrays(GL_TRIANGLES, ...)` quer direto, sem
    precisar de buffer de índices. Gasta mais memória que deduplicar,
    mas pra uma POC (um modelo por vez, não a biblioteca inteira) não
    compensa a complexidade a mais."""

    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """(mínimo, máximo) dos vértices — usado pra centralizar e
        enquadrar a câmera sozinho ao carregar (ver `OrbitCamera.
        enquadrar`), sem o Rafael precisar achar o modelo na mão."""
        xs = [p[0] for p in self.positions]
        ys = [p[1] for p in self.positions]
        zs = [p[2] for p in self.positions]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
    if n < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def parse_obj(path: Path) -> Mesh:
    """Lê um `.obj`. Levanta `ValueError` (mensagem legível) se não achar
    vértice/face nenhum — nunca devolve uma malha vazia em silêncio.

    - Faces com mais de 3 vértices viram um leque de triângulos
      `(0,1,2), (0,2,3), ...` — correto pra faces CONVEXAS, que são a
      esmagadora maioria de export real; não tenta triangular
      concavidade de verdade.
    - `vt` (coordenada de UV) é ignorado — a POC não tem textura ainda.
    - Sem `vn` no arquivo: normal por FACE (produto vetorial de duas
      arestas), igual pros 3 vértices do triângulo — sombreamento
      "faceted" (arestas aparecem), não suave. Correto o bastante pra
      provar o mecanismo; suavizar por vértice fica pra quando isto virar
      fatia de verdade.
    """
    vertices: list[tuple[float, float, float]] = []
    normais_arquivo: list[tuple[float, float, float]] = []
    faces: list[list[tuple[int, int | None]]] = []

    texto = path.read_text(encoding="utf-8", errors="replace")
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split()
        tipo = partes[0]
        if tipo == "v" and len(partes) >= 4:
            vertices.append((float(partes[1]), float(partes[2]), float(partes[3])))
        elif tipo == "vn" and len(partes) >= 4:
            normais_arquivo.append((float(partes[1]), float(partes[2]), float(partes[3])))
        elif tipo == "f" and len(partes) >= 4:
            face: list[tuple[int, int | None]] = []
            for token in partes[1:]:
                campos = token.split("/")
                idx_v = int(campos[0])
                idx_v = idx_v - 1 if idx_v > 0 else len(vertices) + idx_v
                idx_vn = None
                if len(campos) >= 3 and campos[2]:
                    idx_vn = int(campos[2])
                    idx_vn = idx_vn - 1 if idx_vn > 0 else len(normais_arquivo) + idx_vn
                face.append((idx_v, idx_vn))
            faces.append(face)

    if not vertices or not faces:
        raise ValueError(f"{path.name}: nenhum vértice/face encontrado (.obj vazio ou ilegível)")

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []

    for face in faces:
        usa_normal_do_arquivo = all(vn is not None for _v, vn in face)
        normal_face = (0.0, 0.0, 1.0)
        if not usa_normal_do_arquivo:
            p0 = vertices[face[0][0]]
            p1 = vertices[face[1][0]]
            p2 = vertices[face[2][0]]
            normal_face = _norm(_cross(_sub(p1, p0), _sub(p2, p0)))
        for i in range(1, len(face) - 1):
            for idx_v, idx_vn in (face[0], face[i], face[i + 1]):
                positions.append(vertices[idx_v])
                normals.append(normais_arquivo[idx_vn] if usa_normal_do_arquivo
                               else normal_face)

    return Mesh(positions=positions, normals=normals)
