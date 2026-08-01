"""Custom properties: EAV tipado, upsert e sobrevivência via sidecar (Fatia 22)."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import properties as properties_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.sidecar.writer import write_for_asset


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "oak_planks.jpg").write_bytes(b"a" * 50)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, tmp_path
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_criar_e_listar(env):
    conn, _, _ = env
    pid = properties_repo.create_def(conn, "Fornecedor", "text")

    defs = properties_repo.list_defs(conn)

    assert [(d["id"], d["name"], d["value_type"]) for d in defs] == [(pid, "Fornecedor", "text")]


def test_criar_duplicada_devolve_a_existente(env):
    conn, _, _ = env
    a = properties_repo.create_def(conn, "Licença", "text")
    b = properties_repo.create_def(conn, "Licença", "text")
    assert a == b


def test_excluir_e_recriar_revive_em_vez_de_estourar_unique(env):
    conn, _, _ = env
    pid = properties_repo.create_def(conn, "Fornecedor", "text")
    properties_repo.soft_delete_def(conn, pid)
    assert properties_repo.list_defs(conn) == []

    pid2 = properties_repo.create_def(conn, "Fornecedor", "text")

    assert pid2 == pid  # revivida, não duplicada
    assert len(properties_repo.list_defs(conn)) == 1


def test_set_value_para_os_4_tipos(env):
    conn, _, _ = env
    alvo = _id(conn, "oak_planks")
    texto = properties_repo.create_def(conn, "Fornecedor", "text")
    numero = properties_repo.create_def(conn, "Preço", "number")
    booleano = properties_repo.create_def(conn, "Licenciado", "bool")
    data = properties_repo.create_def(conn, "Comprado em", "date")

    properties_repo.set_value(conn, alvo, texto, "ambientCG")
    properties_repo.set_value(conn, alvo, numero, 19.9)
    properties_repo.set_value(conn, alvo, booleano, 1)
    properties_repo.set_value(conn, alvo, data, "2026-01-15")

    valores = properties_repo.get_values_for_asset(conn, alvo)
    assert valores[texto] == "ambientCG"
    assert valores[numero] == 19.9
    assert valores[booleano] == 1
    assert valores[data] == "2026-01-15"


def test_set_value_de_novo_atualiza_upsert(env):
    conn, _, _ = env
    alvo = _id(conn, "oak_planks")
    pid = properties_repo.create_def(conn, "Fornecedor", "text")

    properties_repo.set_value(conn, alvo, pid, "ambientCG")
    properties_repo.set_value(conn, alvo, pid, "Poliigon")

    assert properties_repo.get_values_for_asset(conn, alvo)[pid] == "Poliigon"


def test_clear_value_remove(env):
    conn, _, _ = env
    alvo = _id(conn, "oak_planks")
    pid = properties_repo.create_def(conn, "Fornecedor", "text")
    properties_repo.set_value(conn, alvo, pid, "ambientCG")

    properties_repo.clear_value(conn, alvo, pid)

    assert properties_repo.get_values_for_asset(conn, alvo) == {}


def test_values_by_name_formato_do_sidecar(env):
    conn, _, _ = env
    alvo = _id(conn, "oak_planks")
    pid = properties_repo.create_def(conn, "Fornecedor", "text")
    properties_repo.set_value(conn, alvo, pid, "ambientCG")

    assert properties_repo.values_by_name(conn, alvo) == {"Fornecedor": "ambientCG"}


def test_propriedade_sobrevive_ao_desastre_via_sidecar(env):
    """Banco morre → sidecar devolve a propriedade e o valor."""
    conn, root, tmp_path = env
    alvo = _id(conn, "oak_planks")
    pid = properties_repo.create_def(conn, "Fornecedor", "text")
    properties_repo.set_value(conn, alvo, pid, "ambientCG")
    write_for_asset(conn, root, alvo)
    conn.close()

    conn2 = connect(tmp_path / "renascido.db")
    apply_migrations(conn2)
    lib_id = libraries_repo.get_or_create(conn2, root)
    scan_library(conn2, lib_id, root)

    novo_id = conn2.execute(
        "SELECT id FROM assets WHERE name = 'oak_planks'"
    ).fetchone()["id"]
    assert properties_repo.values_by_name(conn2, novo_id) == {"Fornecedor": "ambientCG"}
    conn2.close()
