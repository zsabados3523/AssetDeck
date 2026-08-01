"""Previews customizados: cópia gerenciada, capa, galeria e soft delete."""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "modelo.blend").write_bytes(b"blend" * 40)
    Image.new("RGB", (64, 64)).save(root / "textura.jpg")
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    # A "imagem do usuário" vem de FORA da biblioteca:
    externa = tmp_path / "meu_render.png"
    Image.new("RGB", (128, 128), (200, 40, 40)).save(externa)
    yield conn, root, tmp_path / "previews", externa
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_add_copia_para_pasta_gerenciada_e_vira_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")

    stored = previews_repo.add(conn, aid, externa, pdir)

    assert stored.parent == pdir          # cópia na pasta do APP…
    assert stored.exists()
    assert externa.exists()               # …e o original do usuário intacto
    galeria = previews_repo.list_for(conn, aid)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "user"


def test_novo_preview_assume_a_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    previews_repo.add(conn, aid, externa, pdir)
    previews_repo.add(conn, aid, externa, pdir)  # segundo

    galeria = previews_repo.list_for(conn, aid)
    assert len(galeria) == 2
    assert [p["is_cover"] for p in galeria] == [0, 1]  # o novo é a capa


def test_set_cover_troca_a_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    previews_repo.add(conn, aid, externa, pdir)
    previews_repo.add(conn, aid, externa, pdir)
    primeiro = previews_repo.list_for(conn, aid)[0]

    previews_repo.set_cover(conn, primeiro["id"])

    galeria = previews_repo.list_for(conn, aid)
    assert [p["is_cover"] for p in galeria] == [1, 0]


def test_grid_ve_cover_path_so_na_visao_agrupada(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    stored = previews_repo.add(conn, aid, externa, pdir)

    agrupado = {r["name"]: r for r in assets_repo.list_for_grid(conn)}
    assert agrupado["modelo"]["cover_path"] == str(stored)
    assert agrupado["textura"]["cover_path"] is None

    expandido = {r["name"]: r for r in assets_repo.list_for_grid(conn, expand_sets=True)}
    assert expandido["modelo"]["cover_path"] is None  # modo expandido: sem capa


def test_soft_delete_tira_da_galeria_mas_preserva_o_arquivo(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    stored = previews_repo.add(conn, aid, externa, pdir)
    pid = previews_repo.list_for(conn, aid)[0]["id"]

    previews_repo.soft_delete(conn, pid)

    assert previews_repo.list_for(conn, aid) == []
    assert stored.exists()  # nada apagado de verdade
    modelo = next(r for r in assets_repo.list_for_grid(conn) if r["name"] == "modelo")
    assert modelo["cover_path"] is None  # a grid volta à thumb normal


def test_add_de_arquivo_inexistente_da_erro_legivel(env):
    conn, _, pdir, _ = env
    with pytest.raises(FileNotFoundError):
        previews_repo.add(conn, _id(conn, "modelo"), pdir / "nada.png", pdir)
