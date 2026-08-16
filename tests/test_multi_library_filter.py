"""Fatia 69: grade/contagem por categoria filtram por biblioteca ativa.

Achado testando a Fatia 68: o banco de dev tinha sobra de uma biblioteca
antiga nunca limpa, e `list_for_grid`/`count_by_category` não filtravam
por `library_id` — a grade misturava as duas, e arrastar um asset da
biblioteca "errada" pro Blender dava "arquivo não encontrado" (o caminho
era montado contra a raiz da biblioteca ATIVA, não a de origem do asset).
"""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.categories import CATEGORIES


@pytest.fixture
def duas_bibliotecas(tmp_path):
    """lib_a: 1 modelo. lib_b: 2 texturas. Tipos e contagens diferentes
    de propósito, pra nenhum assert passar batendo com o total errado."""
    root_a = tmp_path / "lib_a"
    root_a.mkdir()
    (root_a / "cadeira.blend").write_bytes(b"b" * 40)

    root_b = tmp_path / "lib_b"
    root_b.mkdir()
    Image.new("RGB", (64, 64)).save(root_b / "madeira.jpg")
    Image.new("RGB", (64, 64)).save(root_b / "metal.jpg")

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_a = libraries_repo.get_or_create(conn, root_a)
    scan_library(conn, lib_a, root_a)
    lib_b = libraries_repo.get_or_create(conn, root_b)
    scan_library(conn, lib_b, root_b)

    yield conn, lib_a, lib_b
    conn.close()


def test_list_for_grid_sem_library_id_mistura_as_duas(duas_bibliotecas):
    """Comportamento de ANTES da Fatia 69, preservado pra quem não passa
    o argumento novo — não pode quebrar nenhum chamador existente."""
    conn, _lib_a, _lib_b = duas_bibliotecas
    rows = assets_repo.list_for_grid(conn)
    assert len(rows) == 3


def test_list_for_grid_filtra_pela_biblioteca_ativa(duas_bibliotecas):
    conn, lib_a, lib_b = duas_bibliotecas

    rows_a = assets_repo.list_for_grid(conn, library_id=lib_a)
    assert [r["name"] for r in rows_a] == ["cadeira"]

    rows_b = assets_repo.list_for_grid(conn, library_id=lib_b)
    assert {r["name"] for r in rows_b} == {"madeira", "metal"}


def test_count_by_category_filtra_pela_biblioteca_ativa(duas_bibliotecas):
    conn, lib_a, lib_b = duas_bibliotecas

    contagem_a = assets_repo.count_by_category(conn, CATEGORIES, library_id=lib_a)
    assert contagem_a["modelos"] == 1
    assert contagem_a["imagens"] == 0

    contagem_b = assets_repo.count_by_category(conn, CATEGORIES, library_id=lib_b)
    assert contagem_b["modelos"] == 0
    assert contagem_b["imagens"] == 2


def test_count_for_library(duas_bibliotecas):
    conn, lib_a, lib_b = duas_bibliotecas
    assert assets_repo.count_for_library(conn, lib_a) == 1
    assert assets_repo.count_for_library(conn, lib_b) == 2


def test_libraries_list_all(duas_bibliotecas):
    conn, lib_a, lib_b = duas_bibliotecas
    nomes = {lib["id"]: lib["name"] for lib in libraries_repo.list_all(conn)}
    assert nomes == {lib_a: "lib_a", lib_b: "lib_b"}


def test_count_active_e_total_bytes_filtram_pela_biblioteca_ativa(duas_bibliotecas):
    """Achado com screenshot real testando o LibrarySwitcher (Fatia 70): o
    rodapé ("N de M assets", tamanho total) usava count_active/total_bytes
    sem library_id — mesma classe de bug da Fatia 69, só que no rodapé em
    vez da grade."""
    conn, lib_a, lib_b = duas_bibliotecas

    assert assets_repo.count_active(conn) == 3  # sem library_id: soma tudo
    assert assets_repo.count_active(conn, library_id=lib_a) == 1
    assert assets_repo.count_active(conn, library_id=lib_b) == 2

    total_a = assets_repo.total_bytes(conn, library_id=lib_a)
    total_b = assets_repo.total_bytes(conn, library_id=lib_b)
    assert total_a == 40  # só o .blend de 40 bytes
    assert total_b > 0
    assert assets_repo.total_bytes(conn) == total_a + total_b
