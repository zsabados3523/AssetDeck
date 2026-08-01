"""Relocalização em lote (Fatia 19): casar sumidos com achados pelo content_hash."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer import relocator
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "oak_planks.jpg").write_bytes(b"conteudo-da-textura" * 10)
    (root / "pine_bark.jpg").write_bytes(b"outro-conteudo" * 10)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, lib_id
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_arquivo_movido_vira_candidato_e_religa_preservando_identidade(env):
    conn, root, lib_id = env
    asset_id = _id(conn, "oak_planks")
    original_uuid = conn.execute(
        "SELECT uuid FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()["uuid"]
    tag_id = tags_repo.create(conn, "Madeira")
    tags_repo.assign(conn, asset_id, tag_id)
    assets_repo.set_rating(conn, asset_id, 5)

    # move o arquivo de verdade para outra subpasta
    (root / "sub").mkdir()
    (root / "oak_planks.jpg").rename(root / "sub" / "oak_planks_v2.jpg")
    scan_library(conn, lib_id, root)  # cria um asset duplicado + marca o antigo sumido

    candidatos = relocator.find_candidates(conn, lib_id)
    assert len(candidatos) == 1
    par = candidatos[0]
    assert par["missing_name"] == "oak_planks"
    assert par["missing_asset_id"] == asset_id
    assert par["new_rel_path"] == "sub/oak_planks_v2.jpg"

    keeper_id = relocator.relocate(conn, par["missing_file_id"], par["found_file_id"])

    assert keeper_id == asset_id
    asset = conn.execute("SELECT uuid, deleted_at FROM assets WHERE id = ?", (asset_id,)).fetchone()
    assert asset["uuid"] == original_uuid  # identidade preservada
    assert asset["deleted_at"] is None
    arquivo = conn.execute(
        "SELECT rel_path, missing_since FROM files WHERE asset_id = ? AND deleted_at IS NULL",
        (asset_id,),
    ).fetchone()
    assert arquivo["rel_path"] == "sub/oak_planks_v2.jpg"
    assert arquivo["missing_since"] is None
    # tag e nota sobreviveram (é o mesmo asset)
    assert {t["name"] for t in tags_repo.tags_of(conn, asset_id)} == {"Madeira"}
    assert conn.execute("SELECT rating FROM assets WHERE id = ?", (asset_id,)).fetchone()["rating"] == 5
    # o duplicado criado pela varredura foi fundido (soft delete)
    duplicado = conn.execute(
        "SELECT deleted_at FROM assets WHERE id = ?", (par["found_asset_id"],)
    ).fetchone()
    assert duplicado["deleted_at"] is not None


def test_arquivo_apagado_de_vez_nao_vira_candidato_e_nao_some(env):
    conn, root, lib_id = env
    asset_id = _id(conn, "pine_bark")

    (root / "pine_bark.jpg").unlink()  # apagado de verdade, sem substituto
    scan_library(conn, lib_id, root)

    candidatos = relocator.find_candidates(conn, lib_id)
    assert candidatos == []

    asset = conn.execute("SELECT deleted_at FROM assets WHERE id = ?", (asset_id,)).fetchone()
    assert asset["deleted_at"] is None  # nunca apagado do banco
    arquivo = conn.execute(
        "SELECT missing_since FROM files WHERE asset_id = ? AND deleted_at IS NULL",
        (asset_id,),
    ).fetchone()
    assert arquivo["missing_since"] is not None


def test_relocate_com_id_inexistente_devolve_none(env):
    conn, _, _ = env
    assert relocator.relocate(conn, 999999, 999998) is None
