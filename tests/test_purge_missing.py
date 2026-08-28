"""Fatia 100 — 'esquecer' de vez os assets 100% sumidos.

A varredura sozinha NUNCA apaga (só marca `missing_since`, protegendo
contra HD desconectado por engano). Isto aqui é uma ação EXPLÍCITA,
pedida pelo Rafael depois de mover uma leva grande de assets pra fora
da biblioteca de propósito.
"""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "sumido_sozinho.blend").write_bytes(b"a" * 50)
    (root / "presente.blend").write_bytes(b"b" * 50)
    (root / "parcial.blend").write_bytes(b"c" * 50)
    (root / "parcial.png").write_bytes(b"d" * 50)  # segundo arquivo do MESMO asset (agrupado por nome)
    return root


@pytest.fixture
def lib_id(conn, lib):
    return libraries_repo.get_or_create(conn, lib)


def _rescan(conn, lib_id, lib):
    scan_library(conn, lib_id, lib)


def test_asset_totalmente_sumido_e_marcado(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)  # scanner marca missing_since, não apaga

    antes = conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'sumido_sozinho'"
    ).fetchone()
    assert antes["deleted_at"] is None, "a varredura sozinha não deveria apagar"

    marcados = assets_repo.purge_missing(conn, lib_id)
    assert marcados == 1

    depois = conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'sumido_sozinho'"
    ).fetchone()
    assert depois["deleted_at"] is not None


def test_asset_presente_nao_e_tocado(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)

    assets_repo.purge_missing(conn, lib_id)

    presente = conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'presente'"
    ).fetchone()
    assert presente["deleted_at"] is None


def test_asset_com_um_arquivo_sumido_mas_outro_presente_fica_intacto(
    conn, lib, lib_id
):
    """Um asset de 2 arquivos com só UM sumido (o outro ainda presente)
    não pode ser confundido com 'totalmente sumido'. Fusão manual
    (`group_manual`) em vez de confiar no agrupador automático — aqui o
    que importa é testar `purge_missing`, não o agrupador."""
    _rescan(conn, lib_id, lib)
    linhas = conn.execute(
        "SELECT id, name FROM assets WHERE name = 'parcial'"
    ).fetchall()
    assert len(linhas) == 2, "o scanner deveria ter criado 2 assets separados"
    keeper_id = assets_repo.group_manual(conn, [r["id"] for r in linhas])
    assert keeper_id is not None

    (lib / "parcial.png").unlink()
    _rescan(conn, lib_id, lib)

    marcados = assets_repo.purge_missing(conn, lib_id)
    assert marcados == 0, "não é pra marcar: o .blend principal ainda está lá"


def test_previews_perdem_a_capa_mas_o_arquivo_continua_no_disco(
    conn, lib, lib_id, tmp_path
):
    """Mesmo padrão de previews_repo.soft_delete: a cópia da imagem
    permanece — só a linha do banco sai de cena."""
    _rescan(conn, lib_id, lib)
    asset = conn.execute(
        "SELECT id FROM assets WHERE name = 'sumido_sozinho'"
    ).fetchone()
    origem = tmp_path / "capa.png"
    origem.write_bytes(b"png" * 20)
    dest_dir = tmp_path / "previews_dir"
    copiado = previews_repo.add(conn, asset["id"], origem, dest_dir, origin="user")
    assert copiado.is_file()

    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)
    assets_repo.purge_missing(conn, lib_id)

    row = conn.execute(
        "SELECT deleted_at, is_cover FROM previews WHERE asset_id = ?",
        (asset["id"],),
    ).fetchone()
    assert row["deleted_at"] is not None
    assert row["is_cover"] == 0
    assert copiado.is_file(), "o arquivo de preview não deveria ser apagado do disco"


def test_some_da_grade_depois_de_purgado(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)
    assets_repo.purge_missing(conn, lib_id)

    nomes = {r["name"] for r in assets_repo.list_for_grid(conn, library_id=lib_id)}
    assert "sumido_sozinho" not in nomes
    assert "presente" in nomes


def test_busca_por_nome_nao_acha_mais_o_purgado(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)
    assets_repo.purge_missing(conn, lib_id)

    achados = assets_repo.list_for_grid(conn, search="sumido_sozinho", library_id=lib_id)
    assert achados == []


def test_idempotente_rodar_duas_vezes(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)

    primeira = assets_repo.purge_missing(conn, lib_id)
    segunda = assets_repo.purge_missing(conn, lib_id)
    assert primeira == 1
    assert segunda == 0, "já foi marcado — a segunda passada não acha mais candidato"


def test_count_missing_all_bate_com_o_que_purge_marca(conn, lib, lib_id):
    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)

    previsto = assets_repo.count_missing_all(conn, lib_id)
    marcados = assets_repo.purge_missing(conn, lib_id)
    assert previsto == marcados


def test_respeita_library_id_nao_mexe_em_outra_biblioteca(conn, lib, lib_id, tmp_path):
    outra_root = tmp_path / "outra_lib"
    outra_root.mkdir()
    (outra_root / "tambem_sumido.blend").write_bytes(b"x" * 50)
    outra_id = libraries_repo.get_or_create(conn, outra_root)
    scan_library(conn, outra_id, outra_root)
    (outra_root / "tambem_sumido.blend").unlink()
    scan_library(conn, outra_id, outra_root)

    _rescan(conn, lib_id, lib)
    (lib / "sumido_sozinho.blend").unlink()
    _rescan(conn, lib_id, lib)

    marcados = assets_repo.purge_missing(conn, lib_id)
    assert marcados == 1

    outro_asset = conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'tambem_sumido'"
    ).fetchone()
    assert outro_asset["deleted_at"] is None, "não devia mexer na OUTRA biblioteca"
