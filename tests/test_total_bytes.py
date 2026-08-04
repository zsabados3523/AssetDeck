"""`assets_repo.total_bytes` — o tamanho da biblioteca no rodapé (Fatia 49)."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    yield c
    c.close()


def test_biblioteca_vazia_soma_zero(conn):
    """`SUM` de conjunto vazio devolve NULL — sem o COALESCE o rodapé de uma
    biblioteca recém-criada mostraria "None B"."""
    assert assets_repo.total_bytes(conn) == 0


def test_soma_todos_os_arquivos_e_nao_so_os_assets(conn, tmp_path):
    """Um set PBR é UM asset com VÁRIOS arquivos.

    Somar por asset contaria um mapa e ignoraria os outros seis — o rodapé
    diria que a biblioteca é uma fração do que ela é.
    """
    root = tmp_path / "lib"
    (root / "pbr").mkdir(parents=True)
    esperado = 0
    for nome, repeticoes in (
        ("pbr/parede_basecolor.jpg", 100),
        ("pbr/parede_normal.jpg", 150),
        ("pbr/parede_roughness.jpg", 120),
        ("modelo.blend", 300),
    ):
        dados = b"x" * repeticoes
        (root / nome).write_bytes(dados)
        esperado += len(dados)

    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    total = assets_repo.total_bytes(conn)
    assert total == esperado

    # E é MAIOR que a contagem de assets sugeriria: os três mapas viraram
    # menos assets do que arquivos.
    n_arquivos = conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"]
    assert n_arquivos >= assets_repo.count_active(conn)


def test_asset_apagado_nao_conta(conn, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "textura.jpg").write_bytes(b"x" * 500)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    antes = assets_repo.total_bytes(conn)
    assert antes == 500

    conn.execute("UPDATE assets SET deleted_at = '2026-01-01'")
    conn.commit()
    assert assets_repo.total_bytes(conn) == 0
