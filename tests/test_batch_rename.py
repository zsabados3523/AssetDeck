"""Batch rename (Fatia 23) — a única exceção ao somente-leitura.

Testado com arquivos reais num diretório temporário: aqui é a única fatia
que de fato mexe no disco, então a prévia (só leitura) e a aplicação
(escreve) são testadas separadamente, com cuidado extra no que pode falhar.
"""

import pytest

from assetdeck import batch_rename
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.grouper import apply_grouping
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    # set PBR: 2 mapas do mesmo asset (agrupamento roda no scan_library)
    (root / "OldName_basecolor.jpg").write_bytes(b"a" * 50)
    (root / "OldName_normal.jpg").write_bytes(b"b" * 50)
    (root / "outro_arquivo.jpg").write_bytes(b"c" * 50)
    (root / "ja_existe_novo.jpg").write_bytes(b"d" * 50)  # pra testar conflito
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    apply_grouping(conn, lib_id)  # junta OldName_basecolor + OldName_normal num set PBR
    yield conn, root, lib_id
    conn.close()


def _asset_ids(conn, *names):
    marks = ",".join("?" * len(names))
    return [r["id"] for r in conn.execute(
        f"SELECT id FROM assets WHERE name IN ({marks})", names
    )]


def test_build_plan_troca_so_o_nome_preservando_sufixo(env):
    conn, root, lib_id = env
    # "OldName" vira um pbr_set (2 arquivos) — pega o asset por qualquer nome
    ids = [r["id"] for r in conn.execute(
        "SELECT DISTINCT asset_id AS id FROM files WHERE rel_path LIKE 'OldName%'"
    )]

    plano = batch_rename.build_plan(conn, ids, "OldName", "NewName")

    novos = sorted(item.new_rel_path for item in plano)
    assert novos == ["NewName_basecolor.jpg", "NewName_normal.jpg"]


def test_build_plan_ignora_arquivo_sem_match(env):
    conn, root, lib_id = env
    ids = _asset_ids(conn, "outro_arquivo")

    plano = batch_rename.build_plan(conn, ids, "OldName", "X")

    assert plano == []


def test_build_plan_ignora_arquivo_sumido(env):
    conn, root, lib_id = env
    ids = _asset_ids(conn, "outro_arquivo")
    conn.execute(
        "UPDATE files SET missing_since = '2026-01-01T00:00:00' "
        "WHERE rel_path = 'outro_arquivo.jpg'"
    )

    plano = batch_rename.build_plan(conn, ids, "outro", "X")

    assert plano == []


def test_build_plan_busca_vazia_nao_faz_nada(env):
    conn, root, lib_id = env
    ids = _asset_ids(conn, "outro_arquivo")
    assert batch_rename.build_plan(conn, ids, "", "X") == []


def test_find_conflicts_duas_entradas_do_lote_mesmo_nome(env):
    conn, root, lib_id = env
    ids = [r["id"] for r in conn.execute(
        "SELECT DISTINCT asset_id AS id FROM files WHERE rel_path LIKE 'OldName%'"
    )]
    plano = batch_rename.build_plan(conn, ids, "_basecolor", "_X")
    assert [i.new_rel_path for i in plano] == ["OldName_X.jpg"]
    # fabrica uma 2ª entrada do lote que geraria o MESMO novo nome
    plano.append(batch_rename.RenamePlanItem(9999, ids[0], "outro.jpg", "OldName_X.jpg"))

    conflitos = batch_rename.find_conflicts(conn, lib_id, plano)

    assert "OldName_X.jpg" in conflitos


def test_find_conflicts_arquivo_existente_fora_do_lote(env):
    conn, root, lib_id = env
    ids = _asset_ids(conn, "outro_arquivo")
    plano = batch_rename.build_plan(conn, ids, "outro_arquivo", "ja_existe_novo")

    conflitos = batch_rename.find_conflicts(conn, lib_id, plano)

    assert "ja_existe_novo.jpg" in conflitos


def test_find_conflicts_nao_falso_positiva_dentro_do_proprio_lote(env):
    conn, root, lib_id = env
    ids = [r["id"] for r in conn.execute(
        "SELECT DISTINCT asset_id AS id FROM files WHERE rel_path LIKE 'OldName%'"
    )]
    plano = batch_rename.build_plan(conn, ids, "OldName", "NewName")

    conflitos = batch_rename.find_conflicts(conn, lib_id, plano)

    assert conflitos == {}


def test_apply_plan_renomeia_arquivo_e_sidecar_de_verdade(env):
    conn, root, lib_id = env
    (root / "outro_arquivo.jpg.assetdeck.json").write_text('{"assetdeck": 1}')
    ids = _asset_ids(conn, "outro_arquivo")
    plano = batch_rename.build_plan(conn, ids, "outro_arquivo", "renomeado")

    sucesso, falhas = batch_rename.apply_plan(conn, root, plano)

    assert (sucesso, falhas) == (1, 0)
    assert not (root / "outro_arquivo.jpg").exists()
    assert (root / "renomeado.jpg").exists()
    assert (root / "renomeado.jpg.assetdeck.json").exists()
    novo_rel = conn.execute(
        "SELECT rel_path FROM files WHERE asset_id = ?", ids
    ).fetchone()["rel_path"]
    assert novo_rel == "renomeado.jpg"


def test_apply_plan_item_problematico_nao_derruba_o_lote(env):
    conn, root, lib_id = env
    ids = [r["id"] for r in conn.execute(
        "SELECT DISTINCT asset_id AS id FROM files WHERE rel_path LIKE 'OldName%'"
    )]
    plano = batch_rename.build_plan(conn, ids, "OldName", "NewName")
    # sabota um item: o arquivo de origem já não existe mais no disco
    (root / "OldName_normal.jpg").unlink()

    sucesso, falhas = batch_rename.apply_plan(conn, root, plano)

    assert sucesso == 1  # o basecolor foi
    assert falhas == 1   # o normal falhou, mas não travou o resto
    assert (root / "NewName_basecolor.jpg").exists()
