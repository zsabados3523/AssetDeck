"""TagTree — nunca teve teste próprio (mesma lacuna que a FolderTree
tinha antes da Fatia 32). A Fatia 33 mexe no render dos itens, então a
cobertura entra aqui."""

import logging

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import tags as tags_repo
from assetdeck.ui.tag_tree import TagTree

_TAG_ROLE = 32


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def arvore(qapp, conn):
    t = TagTree()
    t.reload(conn)
    return t


def _por_nome(arvore, nome):
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    it = QTreeWidgetItemIterator(arvore)
    while it.value():
        if it.value().text(0) == nome:
            return it.value()
        it += 1
    return None


def test_reload_monta_a_hierarquia(qapp, conn):
    materiais = tags_repo.create(conn, "Materiais")
    tags_repo.create(conn, "Madeira", parent_id=materiais)
    t = TagTree()
    t.reload(conn)

    pai = _por_nome(t, "Materiais")
    assert pai is not None
    assert pai.childCount() == 1
    assert pai.child(0).text(0) == "Madeira"


def test_raiz_sintetica_de_sem_filtro(arvore):
    raiz = arvore.topLevelItem(0)
    assert raiz.text(0) == "(sem filtro de tag)"
    assert raiz.data(0, _TAG_ROLE) is None


def test_item_ganha_icone_mesmo_sem_cor_nem_icone(qapp, conn):
    """Antes da Fatia 33, tag sem cor ficava sem ícone nenhum; agora todas
    recebem ao menos o quadradinho — alinhamento fica consistente."""
    tags_repo.create(conn, "Solta")
    t = TagTree()
    t.reload(conn)

    assert not _por_nome(t, "Solta").icon(0).isNull()


def test_item_com_icone_escolhido(qapp, conn):
    tags_repo.create(conn, "Madeira", color="#B05A1E", icon="tag-madeira")
    t = TagTree()
    t.reload(conn)

    assert not _por_nome(t, "Madeira").icon(0).isNull()


def test_reload_nao_explode_com_icone_que_sumiu(qapp, conn, caplog):
    """Cenário real: SVG renomeado/removido numa versão nova do app. Uma
    tag não pode derrubar a árvore inteira."""
    tags_repo.create(conn, "Fantasma", icon="tag-que-nao-existe-mais")
    t = TagTree()

    with caplog.at_level(logging.WARNING):
        t.reload(conn)  # não pode levantar

    assert _por_nome(t, "Fantasma") is not None
    assert "tag-que-nao-existe-mais" in caplog.text
