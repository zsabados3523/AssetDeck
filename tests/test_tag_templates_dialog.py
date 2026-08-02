"""Diálogo de template de tags (Fatia 35)."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import tags as tags_repo
from assetdeck.ui import tag_templates as tt
from assetdeck.ui.tag_templates_dialog import TagTemplateDialog


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    yield c
    c.close()


def _itens(arvore):
    """Todos os textos da árvore de prévia, achatados."""
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    saida = []
    it = QTreeWidgetItemIterator(arvore)
    while it.value():
        saida.append(it.value())
        it += 1
    return saida


def test_abre_no_balanceado(qapp, conn):
    dlg = TagTemplateDialog(conn)
    assert dlg.nivel == tt.BALANCEADO
    assert len(_itens(dlg.arvore)) == tt.contar(tt.arvore(tt.BALANCEADO))


def test_trocar_de_nivel_recarrega_a_previa(qapp, conn):
    dlg = TagTemplateDialog(conn)
    dlg._trocar_nivel(tt.RESUMIDO)

    assert len(_itens(dlg.arvore)) == 8
    dlg._trocar_nivel(tt.COMPLETO)
    assert len(_itens(dlg.arvore)) == tt.contar(tt.arvore(tt.COMPLETO))


def test_marca_e_esmaece_o_que_ja_existe(qapp, conn):
    from assetdeck.ui import theme

    tags_repo.create(conn, "Materiais")

    dlg = TagTemplateDialog(conn)
    dlg._trocar_nivel(tt.RESUMIDO)
    por_texto = {i.text(0).split("  ")[0]: i for i in _itens(dlg.arvore)}

    assert "já existe" in por_texto["Materiais"].text(0)
    esmaecida = por_texto["Materiais"].foreground(0).color().name().upper()
    assert esmaecida == theme.TEXT_MUTED.upper()
    assert "já existe" not in por_texto["Vegetação"].text(0)


def test_filho_novo_de_pai_existente_nao_parece_desabilitado(qapp, conn):
    """setDisabled num item apaga os FILHOS junto no Qt: 'Materiais (já
    existe)' fazia Madeira/Pedra/Vidro parecerem que também não viriam."""
    tags_repo.create(conn, "Materiais")

    dlg = TagTemplateDialog(conn)  # balanceado: Materiais tem filhos novos
    por_texto = {i.text(0).split("  ")[0]: i for i in _itens(dlg.arvore)}

    assert por_texto["Madeira"].isDisabled() is False
    assert por_texto["Materiais"].isDisabled() is False


def test_resumo_conta_novas_e_existentes(qapp, conn):
    tags_repo.create(conn, "Materiais")

    dlg = TagTemplateDialog(conn)
    dlg._trocar_nivel(tt.RESUMIDO)

    assert dlg.resumo.text() == "7 tags novas · 1 já existem"


def test_abrir_o_dialogo_nao_cria_nada(qapp, conn):
    TagTemplateDialog(conn)
    assert tags_repo.list_tree(conn) == []


def test_aplicar_cria_e_reporta(qapp, conn):
    dlg = TagTemplateDialog(conn)
    dlg._trocar_nivel(tt.RESUMIDO)
    dlg._aplicar()

    assert dlg.aplicado == tt.Resultado(criadas=8, existentes=0)
    assert len(tags_repo.list_tree(conn)) == 8


def test_botao_desliga_quando_nao_ha_o_que_criar(qapp, conn):
    tt.aplicar(conn, tt.COMPLETO)

    dlg = TagTemplateDialog(conn)
    dlg._trocar_nivel(tt.COMPLETO)

    assert dlg.aplicar_btn.isEnabled() is False
