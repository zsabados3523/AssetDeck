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


def _linhas(botao) -> dict:
    """As linhas de biblioteca do menu, por caminho.

    Desde a Fatia 77 cada biblioteca é um `QWidgetAction` com um widget de
    duas linhas (nome + caminho/contagem + bolinha da ativa), não mais um
    `QAction` marcável — `isCheckable()`/`isChecked()` deixaram de existir
    aqui. Quem carrega o estado agora é o `objectName` da bolinha, e o clique
    entra pelo widget, não pelo `trigger()` da ação.
    """
    from PySide6.QtWidgets import QWidgetAction

    achadas = {}
    for acao in botao.menu().actions():
        if isinstance(acao, QWidgetAction) and acao.defaultWidget() is not None:
            w = acao.defaultWidget()
            achadas[w.toolTip()] = w
    return achadas


def _esta_ativa(linha) -> bool:
    from PySide6.QtWidgets import QLabel

    bolinhas = [f.objectName() for f in linha.findChildren(QLabel)]
    return "libDot" in bolinhas


def test_a_biblioteca_ativa_aparece_marcada(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, root_a, root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    linhas = _linhas(botao)
    assert _esta_ativa(linhas[str(root_a)]) is True
    assert _esta_ativa(linhas[str(root_b)]) is False


def _clicar(linha) -> None:
    """Clique de verdade na linha: `QWidgetAction` não dispara por
    `trigger()` — quem responde é o `mouseReleaseEvent` do widget."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    centro = QPointF(linha.width() / 2, linha.height() / 2)
    evento = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, centro, centro,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    linha.mouseReleaseEvent(evento)


def test_clicar_na_biblioteca_ja_ativa_nao_emite_nada(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, root_a, _root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    recebidos = []
    botao.switch_requested.connect(recebidos.append)

    _clicar(_linhas(botao)[str(root_a)])

    assert recebidos == []


def test_clicar_em_outra_biblioteca_emite_switch_requested(qapp, duas_bibliotecas):
    conn, lib_a, _lib_b, _root_a, root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    recebidos = []
    botao.switch_requested.connect(recebidos.append)

    _clicar(_linhas(botao)[str(root_b)])

    assert recebidos == [str(root_b)]


def test_cada_linha_mostra_caminho_e_contagem(qapp, duas_bibliotecas):
    """O que o Rafael chamou de "meio cru" era uma linha só de texto. Cada
    biblioteca agora mostra nome, caminho e quantos assets tem — é o que
    deixa distinguir duas pastas de mesmo nome em lugares diferentes."""
    from PySide6.QtWidgets import QLabel

    conn, lib_a, _lib_b, root_a, _root_b = duas_bibliotecas
    botao = LibrarySwitcher(conn, lib_a)
    linha = _linhas(botao)[str(root_a)]

    textos = [f.text() for f in linha.findChildren(QLabel)]
    assert root_a.name in " ".join(textos)
    meta = next(t for t in textos if "assets" in t)
    assert "1 assets" in meta          # a lib_a tem exatamente 1 imagem
    assert root_a.name in meta         # o fim do caminho sobrevive à elisão


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
