"""Busca FTS e filtros combinados de tipo/pasta/subpastas."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.folder_tree import list_dirs


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def lib(tmp_path, conn):
    """Biblioteca sintética com estrutura de pastas e nomes buscáveis."""
    root = tmp_path / "lib"
    (root / "Texturas" / "Concreto").mkdir(parents=True)
    (root / "Texturas" / "Madeira").mkdir(parents=True)
    (root / "HDRIs").mkdir()
    (root / "Texturas" / "Concreto" / "Concreto Rústico 4K.jpg").write_bytes(b"a" * 50)
    (root / "Texturas" / "Concreto" / "concrete_polished.png").write_bytes(b"b" * 50)
    (root / "Texturas" / "Madeira" / "Wood Oak.jpg").write_bytes(b"c" * 50)
    (root / "Texturas" / "na_raiz_texturas.jpg").write_bytes(b"d" * 50)
    (root / "HDRIs" / "studio_small.hdr").write_bytes(b"e" * 50)
    (root / "solto_na_raiz.png").write_bytes(b"f" * 50)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)  # já reconstrói o FTS
    return root


def _names(rows):
    return sorted(r["name"] for r in rows)


def test_sem_filtro_traz_tudo(conn, lib):
    assert len(assets_repo.list_for_grid(conn)) == 6


def test_busca_por_prefixo(conn, lib):
    rows = assets_repo.list_for_grid(conn, search="conc")
    assert _names(rows) == ["Concreto Rústico 4K", "concrete_polished"]


def test_busca_ignora_acentos(conn, lib):
    rows = assets_repo.list_for_grid(conn, search="rustico")  # sem acento
    assert _names(rows) == ["Concreto Rústico 4K"]


def test_busca_multi_palavra_e_AND(conn, lib):
    assert _names(assets_repo.list_for_grid(conn, search="concreto 4k")) \
        == ["Concreto Rústico 4K"]
    assert assets_repo.list_for_grid(conn, search="concreto oak") == []


def test_busca_com_caracteres_especiais_nao_explode(conn, lib):
    # Aspas, operadores FTS e curingas não podem virar erro de sintaxe
    for maldade in ['"', "AND OR NOT", "conc*", "a:b", "(x)", "   "]:
        assets_repo.list_for_grid(conn, search=maldade)  # não pode levantar


def test_filtro_por_tipo(conn, lib):
    rows = assets_repo.list_for_grid(conn, asset_type="hdri")
    assert _names(rows) == ["studio_small"]


def test_filtro_por_pasta_com_subpastas(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix="Texturas", include_subdirs=True)
    assert len(rows) == 4  # Concreto/2 + Madeira/1 + na_raiz_texturas


def test_filtro_por_pasta_sem_subpastas(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix="Texturas", include_subdirs=False)
    assert _names(rows) == ["na_raiz_texturas"]


def test_raiz_sem_subpastas_mostra_so_arquivos_soltos(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix=None, include_subdirs=False)
    assert _names(rows) == ["solto_na_raiz"]


def test_filtros_combinados(conn, lib):
    rows = assets_repo.list_for_grid(
        conn, search="conc", asset_type="texture",
        dir_prefix="Texturas/Concreto", include_subdirs=True,
    )
    assert len(rows) == 2


def test_lista_de_pastas_para_arvore(conn, lib):
    assert list_dirs(conn) == ["HDRIs", "Texturas", "Texturas/Concreto", "Texturas/Madeira"]


def test_tipos_distintos_para_o_combo(conn, lib):
    assert assets_repo.distinct_types(conn) == ["hdri", "texture"]
