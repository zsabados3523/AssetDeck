"""FolderTree — a árvore de pastas nunca teve teste próprio, apesar de
test_main_window.py:54 afirmar que ela era "testada à parte". A Fatia 32
depende de `select()` reportar sucesso/falha, então a lacuna fecha aqui.
"""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.folder_tree import FolderTree, list_dirs


@pytest.fixture
def conn(tmp_path):
    root = tmp_path / "lib"
    (root / "Modelos" / "Cadeiras").mkdir(parents=True)
    (root / "Texturas").mkdir()
    (root / "Modelos" / "Cadeiras" / "eames.blend").write_bytes(b"b" * 40)
    (root / "Texturas" / "madeira.jpg").write_bytes(b"j" * 40)
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    lib_id = libraries_repo.get_or_create(c, root)
    scan_library(c, lib_id, root)
    yield c
    c.close()


@pytest.fixture
def arvore(qapp, conn):
    t = FolderTree()
    t.reload(conn)
    return t


def test_reload_monta_a_arvore_com_ancestrais(conn):
    assert list_dirs(conn) == ["Modelos", "Modelos/Cadeiras", "Texturas"]


def test_reload_comeca_na_raiz(arvore):
    assert arvore.currentItem().data(0, 32) == ""


def test_select_acha_a_pasta_e_devolve_true(arvore):
    assert arvore.select("Modelos/Cadeiras") is True
    assert arvore.currentItem().data(0, 32) == "Modelos/Cadeiras"


def test_select_expande_os_ancestrais(arvore):
    """Sem isso a pasta fica selecionada dentro de um nó fechado e o
    usuário não vê onde foi parar."""
    arvore.select("Modelos/Cadeiras")
    pai = arvore.currentItem().parent()
    assert pai.isExpanded() is True


def test_select_de_pasta_inexistente_devolve_false_e_nao_mexe(arvore):
    arvore.select("Texturas")
    assert arvore.select("Pasta/Que/Sumiu") is False
    assert arvore.currentItem().data(0, 32) == "Texturas"  # seleção intacta


def test_select_nao_emite_dir_selected(arvore):
    """Quem chama reaplica o filtro — emitir aqui causaria recursão."""
    recebidos = []
    arvore.dir_selected.connect(recebidos.append)

    arvore.select("Texturas")

    assert recebidos == []


def test_clicar_na_arvore_emite_dir_selected(arvore):
    recebidos = []
    arvore.dir_selected.connect(recebidos.append)

    raiz = arvore.topLevelItem(0)
    alvo = next(raiz.child(i) for i in range(raiz.childCount())
                if raiz.child(i).data(0, 32) == "Texturas")
    arvore.setCurrentItem(alvo)

    assert recebidos == ["Texturas"]
