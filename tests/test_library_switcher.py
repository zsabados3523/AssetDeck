"""LibrarySwitcher (Fatia 70): botão no canto da faixa de menus que lista
as bibliotecas conhecidas e deixa trocar de ativa ou anexar uma nova.
"""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui import library_switcher as library_switcher_mod
from assetdeck.ui.library_switcher import LibrarySwitcher


@pytest.fixture
def duas_bibliotecas(tmp_path):
    root_a = tmp_path / "lib_a"
    root_a.mkdir()
    Image.new("RGB", (32, 32)).save(root_a / "img.jpg")

    root_b = tmp_path / "lib_b"
    root_b.mkdir()
    (root_b / "modelo.blend").write_bytes(b"b" * 40)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_a = libraries_repo.get_or_create(conn, root_a)
    scan_library(conn, lib_a, root_a)
    lib_b = libraries_repo.get_or_create(conn, root_b)
    scan_library(conn, lib_b, root_b)

    yield conn, lib_a, lib_b, root_a, root_b
    conn.close()


def test_mostra_o_nome_da_biblioteca_ativa(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, root_a, _root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    assert botao.text() == root_a.name


def test_menu_tem_uma_acao_por_biblioteca_mais_adicionar(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, _root_a, _root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    acoes = [a for a in botao.menu().actions() if not a.isSeparator()]
    assert len(acoes) == 3  # lib_a, lib_b, "Adicionar biblioteca…"
    assert acoes[-1].text() == "Adicionar biblioteca…"


def test_a_biblioteca_ativa_aparece_marcada(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, root_a, root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    acoes = {a.toolTip(): a for a in botao.menu().actions() if a.isCheckable()}
    assert acoes[str(root_a)].isChecked() is True
    assert acoes[str(root_b)].isChecked() is False


def test_clicar_na_biblioteca_ja_ativa_nao_emite_nada(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, root_a, _root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    recebidos = []
    botao.switch_requested.connect(recebidos.append)

    acao_ativa = next(a for a in botao.menu().actions()
                      if a.isCheckable() and a.toolTip() == str(root_a))
    acao_ativa.trigger()

    assert recebidos == []


def test_clicar_em_outra_biblioteca_emite_switch_requested(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, _root_a, root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    recebidos = []
    botao.switch_requested.connect(recebidos.append)

    acao_b = next(a for a in botao.menu().actions()
                  if a.isCheckable() and a.toolTip() == str(root_b))
    acao_b.trigger()

    assert recebidos == [str(root_b)]


def test_adicionar_biblioteca_registra_e_repopula_o_menu(qapp, duas_bibliotecas,
                                                         tmp_path, monkeypatch):
    conn, lib_a, _lib_b, _root_a, _root_b = duas_bibliotecas
    nova = tmp_path / "lib_c"
    nova.mkdir()
    monkeypatch.setattr(
        library_switcher_mod.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(nova)),
    )
    botao = LibrarySwitcher(conn, lib_a)

    acao_adicionar = next(a for a in botao.menu().actions()
                          if a.text() == "Adicionar biblioteca…")
    acao_adicionar.trigger()

    nomes = [lib["root_path"] for lib in libraries_repo.list_all(conn)]
    assert str(nova) in nomes
    acoes = [a for a in botao.menu().actions() if not a.isSeparator()]
    assert len(acoes) == 4  # lib_a, lib_b, lib_c nova, "Adicionar biblioteca…"


def test_adicionar_biblioteca_cancelada_nao_muda_nada(qapp, duas_bibliotecas, monkeypatch):
    conn, lib_a, _lib_b, _root_a, _root_b = duas_bibliotecas
    monkeypatch.setattr(
        library_switcher_mod.QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # usuário cancelou o seletor
    )
    botao = LibrarySwitcher(conn, lib_a)
    antes = len(libraries_repo.list_all(conn))

    acao_adicionar = next(a for a in botao.menu().actions()
                          if a.text() == "Adicionar biblioteca…")
    acao_adicionar.trigger()

    assert len(libraries_repo.list_all(conn)) == antes
