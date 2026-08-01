"""Ratings, favoritos, filtros combinados e extração de dimensões."""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (4096, 2048)).save(root / "grande_4k.jpg")
    Image.new("RGB", (1024, 1024)).save(root / "media_1k.jpg")
    Image.new("RGB", (256, 256)).save(root / "pequena.jpg")
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, lib_id
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_scanner_extrai_dimensoes(env):
    conn, _, _ = env
    row = conn.execute(
        "SELECT width, height, has_alpha, bit_depth FROM files "
        "WHERE rel_path = 'grande_4k.jpg'"
    ).fetchone()
    assert (row["width"], row["height"]) == (4096, 2048)
    assert row["has_alpha"] == 0
    assert row["bit_depth"] == 8


def test_backfill_preenche_dimensoes_de_linhas_antigas(env):
    conn, root, lib_id = env
    # Simula linha pré-Fatia 9 (sem dimensões)
    conn.execute("UPDATE files SET width=NULL, height=NULL WHERE rel_path='media_1k.jpg'")
    conn.commit()

    scan_library(conn, lib_id, root)  # revarredura

    row = conn.execute(
        "SELECT width FROM files WHERE rel_path = 'media_1k.jpg'"
    ).fetchone()
    assert row["width"] == 1024


def test_rating_e_favorito(env):
    conn, _, _ = env
    aid = _id(conn, "grande_4k")
    assets_repo.set_rating(conn, aid, 4)
    assets_repo.set_starred(conn, aid, True)

    row = conn.execute("SELECT rating, starred FROM assets WHERE id = ?", (aid,)).fetchone()
    assert (row["rating"], row["starred"]) == (4, 1)

    assets_repo.set_rating(conn, aid, None)  # limpar nota
    row = conn.execute("SELECT rating FROM assets WHERE id = ?", (aid,)).fetchone()
    assert row["rating"] is None


def test_filtro_por_nota_minima(env):
    conn, _, _ = env
    assets_repo.set_rating(conn, _id(conn, "grande_4k"), 5)
    assets_repo.set_rating(conn, _id(conn, "media_1k"), 2)

    rows = assets_repo.list_for_grid(conn, min_rating=3)
    assert [r["name"] for r in rows] == ["grande_4k"]  # sem nota fica de fora


def test_filtro_so_favoritos(env):
    conn, _, _ = env
    assets_repo.set_starred(conn, _id(conn, "pequena"), True)

    rows = assets_repo.list_for_grid(conn, starred_only=True)
    assert [r["name"] for r in rows] == ["pequena"]


def test_filtro_por_resolucao_minima(env):
    conn, _, _ = env
    assert {r["name"] for r in assets_repo.list_for_grid(conn, min_resolution=2048)} \
        == {"grande_4k"}
    assert {r["name"] for r in assets_repo.list_for_grid(conn, min_resolution=1024)} \
        == {"grande_4k", "media_1k"}


def test_filtros_da_fatia_9_combinam_com_os_antigos(env):
    conn, _, _ = env
    assets_repo.set_rating(conn, _id(conn, "grande_4k"), 5)
    assets_repo.set_starred(conn, _id(conn, "grande_4k"), True)
    assets_repo.set_rating(conn, _id(conn, "media_1k"), 5)

    rows = assets_repo.list_for_grid(
        conn, search="grande", asset_types=["texture"],
        min_rating=4, starred_only=True, min_resolution=2048,
    )
    assert [r["name"] for r in rows] == ["grande_4k"]


def test_rating_e_starred_viajam_no_sidecar_e_voltam(env, tmp_path):
    from assetdeck.sidecar.writer import write_for_asset

    conn, root, _ = env
    aid = _id(conn, "grande_4k")
    assets_repo.set_rating(conn, aid, 5)
    assets_repo.set_starred(conn, aid, True)
    write_for_asset(conn, root, aid)
    conn.close()

    conn2 = connect(tmp_path / "renascido.db")
    apply_migrations(conn2)
    lib_id = libraries_repo.get_or_create(conn2, root)
    scan_library(conn2, lib_id, root)

    row = conn2.execute(
        "SELECT rating, starred FROM assets WHERE name = 'grande_4k'"
    ).fetchone()
    assert (row["rating"], row["starred"]) == (5, 1)
    conn2.close()
