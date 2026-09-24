"""Leitura de geometria, UVs e materiais básicos de arquivos OBJ/MTL."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaterialRange:
    start: int
    count: int
    color: tuple[float, float, float] = (0.72, 0.72, 0.75)
    texture: Path | None = None


@dataclass
class Mesh:
    """Um vértice por CANTO de triângulo usado (não deduplicado) — é o
    formato que `glDrawArrays(GL_TRIANGLES, ...)` quer direto, sem
    precisar de buffer de índices. Gasta mais memória que deduplicar,
    mas pra uma POC (um modelo por vez, não a biblioteca inteira) não
    compensa a complexidade a mais."""

    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    uvs: list[tuple[float, float]] = field(default_factory=list)
    materials: list[MaterialRange] = field(default_factory=list)

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


def _resolve_texture(base: Path, name: str) -> Path | None:
    """Referências podem ser absolutas ou relativas ao MTL; nunca escreve nelas."""
    candidate = Path(name.strip().strip('"'))
    if not candidate.is_absolute():
        candidate = base / candidate
    if candidate.is_file():
        return candidate
    # Alguns packs movem a pasta de mapas para ao lado da pasta do .blend
    # depois de salvar os links. Testa só os dois níveis vizinhos exatos;
    # não faz busca recursiva em bibliotecas grandes nem escolhe homônimos.
    for ancestor in (candidate.parent.parent, candidate.parent.parent.parent):
        for alternate in (ancestor / candidate.name,
                          ancestor / candidate.parent.name / candidate.name):
            if alternate.is_file():
                log.info("Textura realocada: %s → %s", candidate, alternate)
                return alternate
    log.warning("Textura referenciada não encontrada: %s", candidate)
    return None


def _read_mtl(path: Path) -> dict[str, tuple[tuple[float, float, float], Path | None]]:
    result: dict[str, tuple[tuple[float, float, float], Path | None]] = {}
    name: str | None = None
    color = (0.72, 0.72, 0.75)
    texture: Path | None = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        log.warning("Não consegui ler o MTL %s", path, exc_info=True)
        return result
    for line in lines:
        parts = line.strip().split(maxsplit=1)
        if not parts or parts[0].startswith("#"):
            continue
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        if key == "newmtl":
            if name is not None:
                result[name] = (color, texture)
            name, color, texture = value, (0.72, 0.72, 0.75), None
        elif key == "Kd" and name is not None:
            try:
                color = tuple(float(x) for x in value.split()[:3])
                if len(color) != 3:
                    raise ValueError("Kd exige três componentes")
            except ValueError:
                log.warning("Cor Kd inválida em %s: %s", path, line)
        elif key == "map_Kd" and name is not None and value:
            texture = _resolve_texture(path.parent, value)
    if name is not None:
        result[name] = (color, texture)
    return result


def parse_obj(path: Path) -> Mesh:
    """Lê um `.obj`. Levanta `ValueError` (mensagem legível) se não achar
    vértice/face nenhum — nunca devolve uma malha vazia em silêncio.

    - Faces com mais de 3 vértices viram um leque de triângulos
      `(0,1,2), (0,2,3), ...` — correto pra faces CONVEXAS, que são a
      esmagadora maioria de export real; não tenta triangular
      concavidade de verdade.
    - Lê o primeiro conjunto de UVs, `Kd` e `map_Kd` de MTL.
    - Sem `vn` no arquivo: normal por FACE (produto vetorial de duas
      arestas), igual pros 3 vértices do triângulo — sombreamento
      "faceted" (arestas aparecem), não suave. Correto o bastante pra
      provar o mecanismo; suavizar por vértice fica pra quando isto virar
      fatia de verdade.
    """
    vertices: list[tuple[float, float, float]] = []
    normais_arquivo: list[tuple[float, float, float]] = []
    uv_arquivo: list[tuple[float, float]] = []
    faces: list[tuple[list[tuple[int, int | None, int | None]], str | None]] = []
    material_atual: str | None = None
    mtls: dict[str, tuple[tuple[float, float, float], Path | None]] = {}

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
        elif tipo == "vt" and len(partes) >= 3:
            uv_arquivo.append((float(partes[1]), float(partes[2])))
        elif tipo == "mtllib" and len(partes) >= 2:
            # Exportadores como o Blender não põem aspas em nomes com espaços.
            value = linha[len("mtllib"):].strip()
            filenames = [value] if (path.parent / value).is_file() else partes[1:]
            for filename in filenames:
                mtls.update(_read_mtl(path.parent / filename))
        elif tipo == "usemtl":
            material_atual = linha[len("usemtl"):].strip()
        elif tipo == "f" and len(partes) >= 4:
            face: list[tuple[int, int | None, int | None]] = []
            for token in partes[1:]:
                campos = token.split("/")
                idx_v = int(campos[0])
                idx_v = idx_v - 1 if idx_v > 0 else len(vertices) + idx_v
                idx_uv = None
                if len(campos) >= 2 and campos[1]:
                    idx_uv = int(campos[1])
                    idx_uv = idx_uv - 1 if idx_uv > 0 else len(uv_arquivo) + idx_uv
                idx_vn = None
                if len(campos) >= 3 and campos[2]:
                    idx_vn = int(campos[2])
                    idx_vn = idx_vn - 1 if idx_vn > 0 else len(normais_arquivo) + idx_vn
                face.append((idx_v, idx_vn, idx_uv))
            faces.append((face, material_atual))

    if not vertices or not faces:
        raise ValueError(f"{path.name}: nenhum vértice/face encontrado (.obj vazio ou ilegível)")

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    ranges: list[MaterialRange] = []

    for face, material_name in faces:
        usa_normal_do_arquivo = all(vn is not None for _v, vn, _uv in face)
        color, texture = mtls.get(material_name, ((0.72, 0.72, 0.75), None))
        start = len(positions)
        normal_face = (0.0, 0.0, 1.0)
        if not usa_normal_do_arquivo:
            p0 = vertices[face[0][0]]
            p1 = vertices[face[1][0]]
            p2 = vertices[face[2][0]]
            normal_face = _norm(_cross(_sub(p1, p0), _sub(p2, p0)))
        for i in range(1, len(face) - 1):
            for idx_v, idx_vn, idx_uv in (face[0], face[i], face[i + 1]):
                positions.append(vertices[idx_v])
                normals.append(normais_arquivo[idx_vn] if usa_normal_do_arquivo
                               else normal_face)
                uvs.append(uv_arquivo[idx_uv] if idx_uv is not None else (0.0, 0.0))

        count = len(positions) - start
        if count:
            if (ranges and ranges[-1].start + ranges[-1].count == start
                    and ranges[-1].color == color and ranges[-1].texture == texture):
                previous = ranges[-1]
                ranges[-1] = MaterialRange(previous.start, previous.count + count,
                                           color, texture)
            else:
                ranges.append(MaterialRange(start, count, color, texture))

    return Mesh(positions=positions, normals=normals, uvs=uvs, materials=ranges)
