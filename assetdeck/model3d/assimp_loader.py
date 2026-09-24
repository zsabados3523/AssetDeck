"""Leitura de geometria via `assimp_py` — cobre formatos que o parser
caseiro de `.obj` não lê (Fase 6: `.fbx`). Diferente do `.blend`, `.fbx`
tem biblioteca de terceiros de verdade — não precisa do Blender.

`assimp_py` traz a biblioteca nativa dentro do próprio wheel (instala com
`pip install assimp-py`, sem pacote de sistema) — ver TODO.md pra por que
`pyassimp` (o binding "oficial") foi descartado: quebrado no Python 3.12
(usa `distutils`, removido da stdlib).
"""

from __future__ import annotations

import array
from pathlib import Path

from assetdeck.model3d.obj_parser import MaterialRange, Mesh, _resolve_texture

def load_via_assimp(path: Path) -> Mesh:
    """Lê qualquer formato que o assimp suporte, achatado pro mesmo
    formato "um vértice por canto de triângulo" que `Mesh` usa — o
    visualizador não sabe (nem precisa saber) de qual loader a malha
    veio.

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

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    materials: list[MaterialRange] = []

    for malha in cena.meshes:
        start = len(positions)
        verts = array.array("f", malha.vertices)
        norms = array.array("f", malha.normals) if malha.normals else None
        coords = array.array("f", malha.texcoords[0]) if malha.texcoords else None
        indices = array.array("I", malha.indices)
        for i in indices:
            positions.append((verts[3 * i], verts[3 * i + 1], verts[3 * i + 2]))
            if norms is not None:
                normals.append((norms[3 * i], norms[3 * i + 1], norms[3 * i + 2]))
            else:
                # Process_GenNormals deveria sempre preencher — sobra só
                # como rede de segurança pra um formato/caso exótico.
                normals.append((0.0, 0.0, 1.0))
            uvs.append((coords[2 * i], coords[2 * i + 1]) if coords is not None
                       else (0.0, 0.0))

        props = cena.materials[malha.material_index]
        raw_color = props.get("COLOR_DIFFUSE") or (0.72, 0.72, 0.75)
        color = tuple(float(x) for x in raw_color[:3])
        texture_name = props.get("TEXTURE_BASE")
        if not texture_name:
            diffuse = props.get("TEXTURES", {}).get(assimp_py.TextureType_DIFFUSE, [])
            texture_name = diffuse[0] if diffuse else None
        texture = _resolve_texture(path.parent, texture_name) if texture_name else None
        if len(positions) > start:
            materials.append(MaterialRange(start, len(positions) - start, color, texture))

    if not positions:
        raise ValueError(f"{path.name}: malha sem vértices")

    return Mesh(positions=positions, normals=normals, uvs=uvs, materials=materials)
