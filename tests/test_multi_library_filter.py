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
