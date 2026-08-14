"""Ordenação da grid (Fatia 63): nome, modificado, tamanho, resolução."""

import os
import time

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    """3 arquivos com nome, tamanho/resolução e data de modificação
    DESENCONTRADOS de propósito — nome alfabético, tamanho e mtime cada um
    numa ordem diferente — pra nenhum teste passar por acidente batendo
    com outro critério."""
    root = tmp_path / "lib"
    root.mkdir()

    # Nome alfabético: a < b < c. Dimensão (e portanto tamanho em bytes)
    # decresce na mesma ordem do nome — INVERTIDO de propósito da mtime.
    Image.new("RGB", (800, 600)).save(root / "a_grande.jpg")
    Image.new("RGB", (400, 300)).save(root / "b_media.jpg")
    Image.new("RGB", (100, 100)).save(root / "c_pequena.jpg")

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    # mtime na ordem OPOSTA ao nome: c é a mais recente, a é a mais antiga.
    agora = time.time()
    os.utime(root / "a_grande.jpg", (agora - 300, agora - 300))
    os.utime(root / "b_media.jpg", (agora - 200, agora - 200))
    os.utime(root / "c_pequena.jpg", (agora - 100, agora - 100))
    # Reindexar pra o scanner atualizar mtime_ns com os valores forçados.
    scan_library(conn, lib_id, root)

    yield conn
    conn.close()


def _nomes(conn, **kwargs) -> list[str]:
    return [r["name"] for r in assets_repo.list_for_grid(conn, **kwargs)]


def test_padrao_e_nome_crescente(env):
    assert _nomes(env) == ["a_grande", "b_media", "c_pequena"]


def test_nome_decrescente(env):
    assert _nomes(env, sort_by="name", sort_dir="desc") == \
        ["c_pequena", "b_media", "a_grande"]


def test_modificado_mais_recente_primeiro(env):
    assert _nomes(env, sort_by="modified", sort_dir="desc") == \
        ["c_pequena", "b_media", "a_grande"]


def test_modificado_mais_antigo_primeiro(env):
    assert _nomes(env, sort_by="modified", sort_dir="asc") == \
        ["a_grande", "b_media", "c_pequena"]


def test_tamanho_maior_primeiro(env):
    assert _nomes(env, sort_by="size", sort_dir="desc") == \
        ["a_grande", "b_media", "c_pequena"]


def test_tamanho_menor_primeiro(env):
    assert _nomes(env, sort_by="size", sort_dir="asc") == \
        ["c_pequena", "b_media", "a_grande"]


def test_resolucao_maior_primeiro(env):
    assert _nomes(env, sort_by="resolution", sort_dir="desc") == \
        ["a_grande", "b_media", "c_pequena"]


def test_resolucao_menor_primeiro(env):
    assert _nomes(env, sort_by="resolution", sort_dir="asc") == \
        ["c_pequena", "b_media", "a_grande"]


def test_criterio_desconhecido_cai_no_padrao(env):
    """sort_by inválido (ex.: Smart Collection salva com um valor que não
    existe mais) não pode derrubar a consulta — cai no padrão (nome)."""
    assert _nomes(env, sort_by="algo_que_nao_existe") == \
        ["a_grande", "b_media", "c_pequena"]


def test_dentro_de_colecao_manual_ordenacao_e_ignorada(env):
    """Coleção manual (Fatia 17) sempre vence — arrastar define a ordem,
    não faz sentido sort_by competir com isso."""
    from assetdeck.db.repos import collections as collections_repo

    col_id = collections_repo.create(env, "Minha coleção")
    ids = {r["name"]: r["id"] for r in assets_repo.list_for_grid(env)}
    # Adiciona na ordem C, A, B — a ordem de arraste, não a alfabética.
    for nome in ("c_pequena", "a_grande", "b_media"):
        collections_repo.add_items(env, col_id, [ids[nome]])

    assert _nomes(env, collection_id=col_id, sort_by="size", sort_dir="desc") == \
        ["c_pequena", "a_grande", "b_media"]
