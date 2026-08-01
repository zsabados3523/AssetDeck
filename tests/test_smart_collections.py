"""Smart Collections: query salva em JSON, recalculada a cada consulta."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import smart_collections as smart_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "forest_hdri.hdr").write_bytes(b"a" * 50)
    (root / "desert_hdri.hdr").write_bytes(b"b" * 50)
    (root / "oak_planks.jpg").write_bytes(b"c" * 50)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, tmp_path
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_roundtrip_do_json(env):
    conn, _, _ = env
    query = {"asset_types": ["hdri"], "min_rating": 4, "search": None, "tag_id": None}
    smart_id = smart_repo.create(conn, "HDRIs com nota ≥ 4", query)

    registro = smart_repo.get(conn, smart_id)

    assert registro["name"] == "HDRIs com nota ≥ 4"
    assert registro["query"] == query
    assert [r["name"] for r in smart_repo.list_all(conn)] == ["HDRIs com nota ≥ 4"]


def test_aplicar_query_salva_filtra_como_esperado(env):
    conn, _, _ = env
    assets_repo.set_rating(conn, _id(conn, "forest_hdri"), 4)
    assets_repo.set_rating(conn, _id(conn, "desert_hdri"), 2)
    query = {"asset_types": ["hdri"], "min_rating": 4}
    smart_id = smart_repo.create(conn, "HDRIs 4+", query)

    registro = smart_repo.get(conn, smart_id)
    rows = assets_repo.list_for_grid(conn, **registro["query"])

    assert [r["name"] for r in rows] == ["forest_hdri"]


def test_query_recalcula_sozinha_sem_resalvar(env):
    """O critério da fatia: dar nota 5 a um HDRI que antes não entrava e
    consultar de novo (sem tocar na Smart Collection) já mostra ele."""
    conn, _, _ = env
    assets_repo.set_rating(conn, _id(conn, "forest_hdri"), 4)
    query = {"asset_types": ["hdri"], "min_rating": 4}
    smart_id = smart_repo.create(conn, "HDRIs 4+", query)

    antes = assets_repo.list_for_grid(conn, **smart_repo.get(conn, smart_id)["query"])
    assert {r["name"] for r in antes} == {"forest_hdri"}

    assets_repo.set_rating(conn, _id(conn, "desert_hdri"), 5)  # não resalva a query

    depois = assets_repo.list_for_grid(conn, **smart_repo.get(conn, smart_id)["query"])
    assert {r["name"] for r in depois} == {"forest_hdri", "desert_hdri"}


def test_rename_e_soft_delete(env):
    conn, _, _ = env
    smart_id = smart_repo.create(conn, "Original", {"min_rating": 3})

    smart_repo.rename(conn, smart_id, "Renomeada")
    assert smart_repo.get(conn, smart_id)["name"] == "Renomeada"

    smart_repo.soft_delete(conn, smart_id)
    assert smart_repo.get(conn, smart_id) is None
    assert smart_repo.list_all(conn) == []


def test_sobrevive_a_fechar_e_reabrir(env):
    conn, _, tmp_path = env
    smart_repo.create(conn, "HDRIs 4+", {"asset_types": ["hdri"], "min_rating": 4})
    conn.close()

    conn2 = connect(tmp_path / "t.db")
    apply_migrations(conn2)

    salvas = smart_repo.list_all(conn2)
    assert [r["name"] for r in salvas] == ["HDRIs 4+"]
    assert salvas[0]["query"] == {"asset_types": ["hdri"], "min_rating": 4}
    conn2.close()
