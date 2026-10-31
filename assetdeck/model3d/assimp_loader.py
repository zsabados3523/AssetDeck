"""Leitura de geometria via `assimp_py` — cobre formatos que o parser
caseiro de `.obj` não lê (Fase 6: `.fbx`). Diferente do `.blend`, `.fbx`
tem biblioteca de terceiros de verdade — não precisa do Blender.

`assimp_py` traz a biblioteca nativa dentro do próprio wheel (instala com
`pip install assimp-py`, sem pacote de sistema) — ver TODO.md pra por que
`pyassimp` (o binding "oficial") foi descartado: quebrado no Python 3.12
(usa `distutils`, removido da stdlib).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from assetdeck.model3d.obj_parser import MaterialRange, Mesh, _resolve_texture


def load_via_assimp(path: Path) -> Mesh:
    """Lê qualquer formato que o assimp suporte em malha indexada.

    Mantém vértices compartilhados e faixas de índices por material;
    o visualizador não precisa saber de qual formato a malha veio.

    Levanta `ImportError` com mensagem legível se `assimp-py` não
    estiver instalado (formato existe, biblioteca que falta — mensagem
    tem de deixar claro qual dos dois é o problema).
    """
    try:
        import assimp_py
    except ImportError as exc:
        raise ImportError(
            "Falta a biblioteca 'assimp-py' pra ler este formato. Rode: "
            "pip install assimp-py"
        ) from exc

    flags = (
        assimp_py.Process_Triangulate
        | assimp_py.Process_GenNormals
        | assimp_py.Process_JoinIdenticalVertices
        # Sem isto, a malha sai na orientação/escala LOCAL de cada nó da
        # cena, ignorando a transformação que o node carrega — achado
        # testando de verdade com um .fbx exportado do Blender: ele
        # embute uma rotação (Z-up → Y-up, convenção do formato) + escala
        # 100× (m → cm) no nó, não nos vértices. Sem aplicar isso, o
        # modelo aparecia deitado de lado. PreTransformVertices achata a
        # hierarquia de nós de vez, aplicando a transformação de cada um
        # direto nos vértices — perde bone/animação, que este visualizador
        # não usa mesmo.
        | assimp_py.Process_PreTransformVertices
    )
    cena = assimp_py.import_file(str(path), flags)
    if not cena.meshes:
        raise ValueError(f"{path.name}: nenhuma malha encontrada no arquivo")

    position_parts: list[np.ndarray] = []
    normal_parts: list[np.ndarray] = []
    uv_parts: list[np.ndarray] = []
    index_parts: list[np.ndarray] = []
    materials: list[MaterialRange] = []
    vertex_offset = 0
    index_offset = 0

    for malha in cena.meshes:
        indices = np.frombuffer(malha.indices, dtype=np.uint32)
        if not len(indices):
            continue
        verts = np.frombuffer(malha.vertices, dtype=np.float32).reshape(-1, 3)
        position_parts.append(verts.copy())
        index_parts.append(indices + vertex_offset)
        if malha.normals:
            norms = np.frombuffer(malha.normals, dtype=np.float32).reshape(-1, 3)
            normal_parts.append(norms.copy())
        else:
            # Process_GenNormals deveria preencher; mantém um fallback
            # explícito para formatos que não ofereçam normais.
            fallback = np.zeros((len(verts), 3), dtype=np.float32)
            fallback[:, 2] = 1.0
            normal_parts.append(fallback)
        if malha.texcoords:
            coords = np.frombuffer(malha.texcoords[0], dtype=np.float32).reshape(-1, 2)
            uv_parts.append(coords.copy())
        else:
            uv_parts.append(np.zeros((len(verts), 2), dtype=np.float32))

        props = cena.materials[malha.material_index]
        raw_color = props.get("COLOR_DIFFUSE") or (0.72, 0.72, 0.75)
        color = tuple(float(x) for x in raw_color[:3])
        diffuse = props.get("TEXTURES", {}).get(assimp_py.TextureType_DIFFUSE, [])
        texture_name = diffuse[0] if diffuse else props.get("TEXTURE_BASE")
        texture = _resolve_texture(path.parent, texture_name) if texture_name else None
        materials.append(MaterialRange(index_offset, len(indices), color, texture,
                                       props.get("NAME")))
        vertex_offset += len(verts)
        index_offset += len(indices)

    if not position_parts:
        raise ValueError(f"{path.name}: malha sem vértices")

    return Mesh(positions=np.concatenate(position_parts),
                normals=np.concatenate(normal_parts),
                uvs=np.concatenate(uv_parts), materials=materials,
                indices=np.concatenate(index_parts))
