"""Parser de .obj (Fase 6 — POC do visualizador 3D)."""

import pytest

from assetdeck.model3d.obj_parser import parse_obj


def _escrever(tmp_path, nome, conteudo):
    caminho = tmp_path / nome
    caminho.write_text(conteudo)
    return caminho


def test_triangulo_simples(tmp_path):
    caminho = _escrever(tmp_path, "tri.obj", """
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
""")
    mesh = parse_obj(caminho)
    assert mesh.positions == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert len(mesh.normals) == 3
    # face no plano XY, sentido anti-horário — normal aponta pra +Z
    for n in mesh.normals:
        assert n == pytest.approx((0.0, 0.0, 1.0))


def test_face_com_4_vertices_vira_leque_de_2_triangulos(tmp_path):
    caminho = _escrever(tmp_path, "quad.obj", """
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
f 1 2 3 4
""")
    mesh = parse_obj(caminho)
    assert len(mesh.positions) == 6  # 2 triângulos × 3 vértices


def test_indices_negativos_sao_relativos_ao_fim(tmp_path):
    """`.obj` permite referenciar vértice por posição relativa (-1 = o
    último `v` lido até ali) — usado por alguns exportadores."""
    caminho = _escrever(tmp_path, "neg.obj", """
v 0 0 0
v 1 0 0
v 0 1 0
f -3 -2 -1
""")
    mesh = parse_obj(caminho)
    assert mesh.positions == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]


def test_usa_normal_do_arquivo_quando_tem(tmp_path):
    caminho = _escrever(tmp_path, "vn.obj", """
v 0 0 0
v 1 0 0
v 0 1 0
vn 0 0 -1
f 1//1 2//1 3//1
""")
    mesh = parse_obj(caminho)
    assert all(n == (0.0, 0.0, -1.0) for n in mesh.normals)


def test_vt_e_ignorado_sem_quebrar(tmp_path):
    caminho = _escrever(tmp_path, "vt.obj", """
v 0 0 0
v 1 0 0
v 0 1 0
vt 0 0
vt 1 0
vt 0 1
f 1/1 2/2 3/3
""")
    mesh = parse_obj(caminho)
    assert len(mesh.positions) == 3


def test_comentarios_e_linhas_vazias_sao_ignorados(tmp_path):
    caminho = _escrever(tmp_path, "comentado.obj", """
# comentário no topo

v 0 0 0
v 1 0 0
v 0 1 0

# outro comentário
f 1 2 3
""")
    mesh = parse_obj(caminho)
    assert len(mesh.positions) == 3


def test_arquivo_sem_face_levanta_valueerror_legivel(tmp_path):
    caminho = _escrever(tmp_path, "so_vertices.obj", "v 0 0 0\nv 1 0 0\nv 0 1 0\n")
    with pytest.raises(ValueError, match="so_vertices.obj"):
        parse_obj(caminho)


def test_arquivo_vazio_levanta_valueerror(tmp_path):
    caminho = _escrever(tmp_path, "vazio.obj", "")
    with pytest.raises(ValueError):
        parse_obj(caminho)


def test_bounds_da_o_minimo_e_o_maximo(tmp_path):
    caminho = _escrever(tmp_path, "bbox.obj", """
v -1 -2 -3
v 4 5 6
v 0 0 0
f 1 2 3
""")
    mesh = parse_obj(caminho)
    minimo, maximo = mesh.bounds()
    assert minimo == (-1.0, -2.0, -3.0)
    assert maximo == (4.0, 5.0, 6.0)
