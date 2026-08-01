"""O schema v1 nasce completo e as regras do banco realmente funcionam."""

import sqlite3

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations, current_version
from assetdeck.db.repos import assets as assets_repo

TABELAS_V1 = {
    "libraries", "assets", "files",
    "tags", "tag_aliases", "asset_tags",
    "previews", "property_defs", "property_values",
    "collections", "collection_items", "smart_collections",
    "assets_fts",
}


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


def _insert_library_and_asset(conn, uuid="u-1"):
    conn.execute("INSERT INTO libraries (id, name, root_path) VALUES (1, 'Test', '/x')")
    conn.execute(
        "INSERT INTO assets (uuid, library_id, name, asset_type) "
        "VALUES (?, 1, 'Asset', 'texture')",
        (uuid,),
    )


def test_todas_as_tabelas_do_schema_v1_existem(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()
    existentes = {r["name"] for r in rows}
    faltando = TABELAS_V1 - existentes
    assert not faltando, f"Tabelas ausentes do schema v1: {faltando}"


def test_versao_final_e_4(conn):
    # 001 inicial + 002 group_locked + 003 hidden + 004 is_dependency
    assert current_version(conn) == 4


def test_reaplicar_migrations_e_noop(conn):
    assert apply_migrations(conn) == 4  # não explode nem duplica


def test_migration_002_group_locked_default_zero(conn):
    _insert_library_and_asset(conn)
    row = conn.execute("SELECT group_locked FROM assets WHERE uuid = 'u-1'").fetchone()
    assert row["group_locked"] == 0


def test_asset_type_invalido_e_rejeitado(conn):
    _insert_library_and_asset(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO assets (uuid, library_id, name, asset_type) "
            "VALUES ('u-2', 1, 'X', 'banana')"
        )


def test_rating_fora_de_1_a_5_e_rejeitado(conn):
    _insert_library_and_asset(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE assets SET rating = 7 WHERE uuid = 'u-1'")


def test_map_role_invalido_e_rejeitado(conn):
    _insert_library_and_asset(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO files (asset_id, rel_path, size_bytes, mtime_ns, map_role) "
            "VALUES (1, 'a.jpg', 10, 0, 'colorido')"
        )


def test_file_orfao_e_rejeitado(conn):
    # foreign_keys=ON de verdade: file apontando para asset inexistente falha
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO files (asset_id, rel_path, size_bytes, mtime_ns) "
            "VALUES (999, 'a.jpg', 10, 0)"
        )


def test_tags_raiz_nao_podem_duplicar_nome(conn):
    conn.execute("INSERT INTO tags (name) VALUES ('Madeira')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tags (name) VALUES ('Madeira')")


def test_count_active_ignora_soft_deleted(conn):
    _insert_library_and_asset(conn, uuid="u-1")
    conn.execute(
        "INSERT INTO assets (uuid, library_id, name, asset_type, deleted_at) "
        "VALUES ('u-2', 1, 'Apagado', 'hdri', datetime('now'))"
    )
    assert assets_repo.count_active(conn) == 1
