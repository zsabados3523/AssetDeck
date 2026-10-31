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


def test_vt_e_lido(tmp_path):
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
    assert mesh.uvs == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]


def test_mtl_cor_textura_e_troca_de_material(tmp_path):
    (tmp_path / "cor.png").write_bytes(b"arquivo referenciado")
    (tmp_path / "materiais.mtl").write_text(
        "newmtl Azul\nKd 0.1 0.2 0.8\nmap_Kd cor.png\n"
        "newmtl Vermelho\nKd 0.9 0.1 0.1\n")
    caminho = _escrever(tmp_path, "duas_faces.obj", """
mtllib materiais.mtl
v 0 0 0
v 1 0 0
v 0 1 0
v 1 1 0
vt 0 0
vt 1 0
vt 0 1
vt 1 1
usemtl Azul
f 1/1 2/2 3/3
usemtl Vermelho
f 2/2 4/4 3/3
""")
    mesh = parse_obj(caminho)
    assert [(r.start, r.count) for r in mesh.materials] == [(0, 3), (3, 3)]
    assert mesh.materials[0].color == pytest.approx((0.1, 0.2, 0.8))
    assert mesh.materials[0].texture == tmp_path / "cor.png"
    assert mesh.materials[1].color == pytest.approx((0.9, 0.1, 0.1))


def test_textura_realocada_para_pasta_irma_do_modelo(tmp_path):
    (tmp_path / "modelos" / "maps").mkdir(parents=True)
    imagem = tmp_path / "modelos" / "maps" / "cor.png"
    imagem.write_bytes(b"referencia")
    modelo = tmp_path / "modelos" / "cubo"
    modelo.mkdir(parents=True)
    (modelo / "cubo.mtl").write_text(
        f"newmtl Cor\nmap_Kd {modelo / 'maps' / 'cor.png'}\n")
    caminho = _escrever(modelo, "cubo.obj", "mtllib cubo.mtl\n"
                        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
                        "usemtl Cor\nf 1 2 3\n")
    assert parse_obj(caminho).materials[0].texture == imagem


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
