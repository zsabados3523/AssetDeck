"""Duplicados por conteúdo visual (Fatia 20): mesma textura, resoluções diferentes."""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer import duplicates as duplicates_finder
from assetdeck.indexer.scanner import scan_library


def _salvar_gradiente(path, size, invertido=False):
    """Gradiente diagonal — cor sólida colidiria (dHash de área uniforme é
    sempre 0000...0), por isso o padrão precisa variar de verdade."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            v = int(255 * (x + y) / (size[0] + size[1]))
            if invertido:
                v = 255 - v
            px[x, y] = (v, v, v)
    img.save(path)


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    _salvar_gradiente(root / "concreto_1k.jpg", (256, 256))
    _salvar_gradiente(root / "concreto_4k.jpg", (1024, 1024))  # mesma textura, outra resolução
    _salvar_gradiente(root / "grama.jpg", (256, 256), invertido=True)  # diferente

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_mesma_textura_em_resolucoes_diferentes_forma_um_grupo(env):
    conn, lib_id = env

    grupos = duplicates_finder.find_duplicate_groups(conn, lib_id)

    assert len(grupos) == 1
    nomes = {m["name"] for m in grupos[0]}
    assert nomes == {"concreto_1k", "concreto_4k"}


def test_textura_diferente_fica_de_fora_do_grupo(env):
    conn, lib_id = env

    grupos = duplicates_finder.find_duplicate_groups(conn, lib_id)

    todos_nomes = {m["name"] for g in grupos for m in g}
    assert "grama" not in todos_nomes


def test_ocultar_um_duplicado_some_da_grade_padrao_mas_reversivel(env):
    conn, lib_id = env
    alvo = _id(conn, "concreto_1k")

    assets_repo.set_hidden(conn, alvo, True)

    visiveis = {r["name"] for r in assets_repo.list_for_grid(conn)}
    assert "concreto_1k" not in visiveis
    com_ocultos = {r["name"] for r in assets_repo.list_for_grid(conn, include_hidden=True)}
    assert "concreto_1k" in com_ocultos


def test_asset_ja_oculto_nao_aparece_de_novo_como_candidato(env):
    conn, lib_id = env
    assets_repo.set_hidden(conn, _id(conn, "concreto_1k"), True)

    grupos = duplicates_finder.find_duplicate_groups(conn, lib_id)

    assert grupos == []  # só sobrou 1 visível do grupo — não é mais duplicata
