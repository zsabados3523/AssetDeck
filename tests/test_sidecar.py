"""Sidecars .json: escrita, restauração pós-desastre e casos degenerados."""

import json

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.sidecar.reader import read_sidecar, restorable_fields
from assetdeck.sidecar.writer import sidecar_path, write_for_asset


@pytest.fixture
def env(tmp_path):
    """Banco + biblioteca sintética indexada."""
    root = tmp_path / "lib"
    root.mkdir()
    (root / "concreto.jpg").write_bytes(b"x" * 100)
    (root / "ceu.hdr").write_bytes(b"y" * 100)
    conn = connect(tmp_path / "test.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, tmp_path
    conn.close()


def _asset_id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_sidecar_e_criado_ao_lado_com_conteudo_correto(env):
    conn, root, _ = env
    aid = _asset_id(conn, "concreto")
    assets_repo.set_notes(conn, aid, "usei na fachada do projeto X")

    dest = write_for_asset(conn, root, aid)

    assert dest == root / "concreto.jpg.assetdeck.json"
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["assetdeck"] == 1
    assert data["name"] == "concreto"
    assert data["notes"] == "usei na fachada do projeto X"
    assert data["files"] == ["concreto.jpg"]
    # O asset original está intocado:
    assert (root / "concreto.jpg").read_bytes() == b"x" * 100


def test_desastre_total_recupera_nota_e_uuid_do_sidecar(env):
    """O teste-chave da fatia: banco morre, sidecar ressuscita os metadados."""
    conn, root, tmp_path = env
    aid = _asset_id(conn, "concreto")
    assets_repo.set_notes(conn, aid, "nota preciosa")
    write_for_asset(conn, root, aid)
    uuid_original = conn.execute(
        "SELECT uuid FROM assets WHERE id = ?", (aid,)
    ).fetchone()["uuid"]
    conn.close()

    # DESASTRE: banco novo, do zero (como se o .db tivesse corrompido)
    conn2 = connect(tmp_path / "renascido.db")
    apply_migrations(conn2)
    lib_id = libraries_repo.get_or_create(conn2, root)
    stats = scan_library(conn2, lib_id, root)

    assert stats.restored == 1
    row = conn2.execute("SELECT uuid, notes FROM assets WHERE name = 'concreto'").fetchone()
    assert row["notes"] == "nota preciosa"
    assert row["uuid"] == uuid_original  # identidade sobreviveu à morte do banco
    conn2.close()


def test_sidecar_corrompido_e_ignorado_sem_derrubar_a_varredura(env):
    conn, root, tmp_path = env
    (root / "novo.png").write_bytes(b"z" * 50)
    sidecar_path(root / "novo.png").write_text("{nao e json valido", encoding="utf-8")

    lib_id = libraries_repo.get_or_create(conn, root)
    stats = scan_library(conn, lib_id, root)

    assert stats.added == 1       # o arquivo entrou normalmente…
    assert stats.restored == 0    # …só que sem restauração
    assert stats.errors == 0


def test_uuid_duplicado_no_sidecar_gera_uuid_novo(env):
    """Arquivo copiado junto com o sidecar não pode roubar a identidade."""
    conn, root, _ = env
    aid = _asset_id(conn, "concreto")
    write_for_asset(conn, root, aid)

    # Copia arquivo + sidecar (mesmo uuid dentro!)
    (root / "concreto_copia.jpg").write_bytes(b"x" * 100)
    original = (root / "concreto.jpg.assetdeck.json").read_text(encoding="utf-8")
    (root / "concreto_copia.jpg.assetdeck.json").write_text(original, encoding="utf-8")

    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    uuids = [r["uuid"] for r in conn.execute(
        "SELECT uuid FROM assets WHERE name LIKE 'concreto%'"
    )]
    assert len(uuids) == 2
    assert len(set(uuids)) == 2  # identidades distintas


def test_restorable_fields_descarta_lixo_campo_a_campo():
    dados = {
        "assetdeck": 1, "uuid": "abc12345", "name": "  Bom Nome  ",
        "rating": 99, "starred": "sim", "notes": 42,
    }
    campos = restorable_fields(dados)
    assert campos == {"uuid": "abc12345", "name": "Bom Nome"}


def test_read_sidecar_de_versao_desconhecida_e_ignorado(tmp_path):
    p = tmp_path / "x.jpg.assetdeck.json"
    p.write_text(json.dumps({"assetdeck": 2, "uuid": "abc"}), encoding="utf-8")
    assert read_sidecar(p) is None
