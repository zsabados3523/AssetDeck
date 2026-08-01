"""Coleções manuais: hierarquia, itens em ordem manual e sobrevivência no banco."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import collections as collections_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "oak_planks.jpg").write_bytes(b"a" * 50)
    (root / "pine_bark.jpg").write_bytes(b"b" * 50)
    (root / "steel_plate.jpg").write_bytes(b"c" * 50)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, tmp_path
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_hierarquia_e_descendants(env):
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    fachada = collections_repo.create(conn, "Fachada", parent_id=casa)

    assert set(collections_repo.descendants(conn, casa)) == {casa, fachada}
    nomes = {r["name"] for r in collections_repo.list_tree(conn)}
    assert nomes == {"Projeto Casa X", "Fachada"}


def test_add_items_preserva_ordem_de_chegada(env):
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    steel = _id(conn, "steel_plate")
    oak = _id(conn, "oak_planks")
    pine = _id(conn, "pine_bark")

    collections_repo.add_items(conn, casa, [steel, oak, pine])

    rows = assets_repo.list_for_grid(conn, collection_id=casa)
    assert [r["name"] for r in rows] == ["steel_plate", "oak_planks", "pine_bark"]


def test_add_items_duplicado_nao_reordena(env):
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    steel = _id(conn, "steel_plate")
    oak = _id(conn, "oak_planks")
    collections_repo.add_items(conn, casa, [steel, oak])

    n = collections_repo.add_items(conn, casa, [steel])  # já está lá

    assert n == 0
    rows = assets_repo.list_for_grid(conn, collection_id=casa)
    assert [r["name"] for r in rows] == ["steel_plate", "oak_planks"]


def test_filtro_por_colecao_mostra_so_os_itens_dela(env):
    """O critério da fatia: criar, arrastar 5 (aqui 2), clicar e ver só esses."""
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    outra = collections_repo.create(conn, "Outro projeto")
    collections_repo.add_items(conn, casa, [_id(conn, "oak_planks"), _id(conn, "pine_bark")])
    collections_repo.add_items(conn, outra, [_id(conn, "steel_plate")])

    rows = assets_repo.list_for_grid(conn, collection_id=casa)

    assert {r["name"] for r in rows} == {"oak_planks", "pine_bark"}


def test_remove_item_tira_da_colecao(env):
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    oak = _id(conn, "oak_planks")
    collections_repo.add_items(conn, casa, [oak, _id(conn, "pine_bark")])

    collections_repo.remove_item(conn, casa, oak)

    rows = assets_repo.list_for_grid(conn, collection_id=casa)
    assert [r["name"] for r in rows] == ["pine_bark"]


def test_soft_delete_cascateia_para_subcolecoes(env):
    conn, _, _ = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    fachada = collections_repo.create(conn, "Fachada", parent_id=casa)
    collections_repo.add_items(conn, fachada, [_id(conn, "oak_planks")])

    caidas = collections_repo.soft_delete(conn, casa)

    assert caidas == 2  # casa + fachada
    assert collections_repo.list_tree(conn) == []


def test_colecao_e_itens_sobrevivem_a_fechar_e_reabrir(env):
    """'fechar e reabrir mantém tudo' — mesmo arquivo .db, nova conexão."""
    conn, root, tmp_path = env
    casa = collections_repo.create(conn, "Projeto Casa X")
    collections_repo.add_items(
        conn, casa, [_id(conn, "oak_planks"), _id(conn, "pine_bark")]
    )
    conn.close()

    conn2 = connect(tmp_path / "t.db")
    apply_migrations(conn2)

    arvore = collections_repo.list_tree(conn2)
    assert [r["name"] for r in arvore] == ["Projeto Casa X"]
    rows = assets_repo.list_for_grid(conn2, collection_id=arvore[0]["id"])
    assert {r["name"] for r in rows} == {"oak_planks", "pine_bark"}
    conn2.close()
