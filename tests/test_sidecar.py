"""Sidecars .json: escrita, restauração pós-desastre e casos degenerados."""

import json

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import tags as tags_repo
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
    assert data["assetdeck"] == 2  # Fatia 45: formato 2, tags com cor/ícone
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


def test_desastre_total_recupera_cor_e_icone_da_tag(env):
    """O teste-chave da Fatia 45: cor e ícone de uma tag sobrevivem a
    apagar o banco e reindexar — não só o nome (buraco desde a Fatia 8,
    ganhado de novo pelo ícone na Fatia 33)."""
    conn, root, tmp_path = env
    aid = _asset_id(conn, "concreto")

    tid = tags_repo.get_or_create_path(conn, "Materiais/Concreto")
    tags_repo.set_color(conn, tid, "#a1b2c3")
    tags_repo.set_icon(conn, tid, "tag-concreto")
    conn.execute(
        "INSERT INTO asset_tags (asset_id, tag_id, source) VALUES (?, ?, 'manual')",
        (aid, tid),
    )
    conn.commit()
    write_for_asset(conn, root, aid)
    conn.close()

    # DESASTRE: banco novo, do zero
    conn2 = connect(tmp_path / "renascido.db")
    apply_migrations(conn2)
    lib_id = libraries_repo.get_or_create(conn2, root)
    scan_library(conn2, lib_id, root)

    row = conn2.execute("SELECT color, icon FROM tags WHERE name = 'Concreto'").fetchone()
    assert row["color"] == "#a1b2c3"
    assert row["icon"] == "tag-concreto"
    # O ancestral (raiz do caminho) também sobrevive, mesmo sem cor/ícone
    raiz = conn2.execute("SELECT name FROM tags WHERE name = 'Materiais'").fetchone()
    assert raiz is not None
    conn2.close()


def test_sidecar_formato_1_antigo_ainda_restaura_tags_sem_cor(env):
    """Sidecar escrito ANTES da Fatia 45 (formato 1, tags como lista de
    strings) continua restaurando a tag — só sem cor/ícone, que nunca
    existiu nesse formato. Rafael tem sidecars assim na biblioteca real."""
    conn, root, tmp_path = env
    (root / "novo.png").write_bytes(b"w" * 40)
    sidecar_path(root / "novo.png").write_text(
        json.dumps({"assetdeck": 1, "uuid": "def45678", "tags": ["Materiais/Pedra"]}),
        encoding="utf-8",
    )
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    aid = _asset_id(conn, "novo")
    nomes = [t["name"] for t in tags_repo.tags_of(conn, aid)]
    assert nomes == ["Pedra"]


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
    # Fatia 45 introduziu o formato 2 (tags com cor/ícone) — só uma versão
    # REALMENTE desconhecida (3+) deve ser rejeitada agora.
    p = tmp_path / "x.jpg.assetdeck.json"
    p.write_text(json.dumps({"assetdeck": 3, "uuid": "abc"}), encoding="utf-8")
    assert read_sidecar(p) is None


def test_read_sidecar_aceita_formato_1_e_2(tmp_path):
    for versao in (1, 2):
        p = tmp_path / f"v{versao}.jpg.assetdeck.json"
        p.write_text(json.dumps({"assetdeck": versao, "uuid": "abc12345"}), encoding="utf-8")
        assert read_sidecar(p) is not None
