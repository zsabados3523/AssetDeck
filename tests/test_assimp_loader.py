"""Loader via assimp (Fase 6 — .fbx e outros formatos que o assimp lê).

Usa um .obj simples como fixture: `assimp_py.import_file` não liga pra
extensão do arquivo de teste, só pro CONTEÚDO — o que este teste cobre é
a conversão do resultado do assimp pro `Mesh` da assetdeck (achatamento
de índices, posição+normal), não o parser interno do assimp em si (já é
biblioteca madura e testada por fora). Não precisa de arquivo .fbx real
nem do Blender.
"""

import sys

import pytest

from assetdeck.model3d.assimp_loader import load_via_assimp


def _tem_assimp() -> bool:
    try:
        import assimp_py  # noqa: F401
    except ImportError:
        return False
    return True


requer_assimp = pytest.mark.skipif(not _tem_assimp(),
                                   reason="assimp-py não instalado neste ambiente")


def test_sem_assimp_instalado_da_mensagem_legivel(tmp_path, monkeypatch):
    """`sys.modules[nome] = None` é o jeito padrão de forçar ImportError
    num import, mesmo com o pacote de verdade instalado neste ambiente —
    testa a MENSAGEM sem depender de desinstalar nada, e roda sempre
    (não é pulado mesmo sem assimp-py instalado)."""
    monkeypatch.setitem(sys.modules, "assimp_py", None)
    with pytest.raises(ImportError, match="assimp-py"):
        load_via_assimp(tmp_path / "qualquer.fbx")


@requer_assimp
def test_le_um_triangulo_simples(tmp_path):
    caminho = tmp_path / "tri.obj"
    caminho.write_text("""
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
""")
    mesh = load_via_assimp(caminho)
    assert len(mesh.positions) == 3
    assert len(mesh.normals) == 3
    for n in mesh.normals:
        assert n == pytest.approx((0.0, 0.0, 1.0), abs=1e-5)


@requer_assimp
def test_face_com_4_vertices_vira_2_triangulos(tmp_path):
    caminho = tmp_path / "quad.obj"
    caminho.write_text("""
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
""")
    mesh = load_via_assimp(caminho)
    assert len(mesh.positions) == 6  # 2 triângulos × 3 vértices (Process_Triangulate)


@requer_assimp
def test_arquivo_sem_malha_levanta_valueerror(tmp_path):
    caminho = tmp_path / "vazio.obj"
    caminho.write_text("# só um comentário, nenhum vértice\n")
    with pytest.raises(ValueError):
        load_via_assimp(caminho)
