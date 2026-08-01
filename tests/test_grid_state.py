"""A grid preserva rolagem e seleção ao recarregar (bug relatado pelo Rafael)."""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel, AssetGridView


@pytest.fixture
def grid(qapp, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    for i in range(60):  # itens suficientes para haver rolagem
        Image.new("RGB", (32, 32)).save(root / f"asset_{i:03d}.jpg")
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    pipeline = ThumbnailPipeline(tmp_path / "thumbs")
    modelo = AssetGridModel(conn, root, pipeline)
    view = AssetGridView()
    view.setModel(modelo)
    view.resize(400, 300)
    modelo.reload()
    view.show()
    qapp.processEvents()
    yield view, modelo, conn
    pipeline.shutdown()
    view.close()
    conn.close()


def test_index_of_asset_encontra_a_linha(grid):
    _view, modelo, _conn = grid
    linha5 = modelo.row_at(modelo.index(5))
    idx = modelo.index_of_asset(linha5["id"])
    assert idx is not None and idx.row() == 5


def test_index_of_asset_devolve_none_para_id_ausente(grid):
    _view, modelo, _conn = grid
    assert modelo.index_of_asset(999999) is None


def test_grid_nao_deixa_o_usuario_reposicionar_os_cards(grid):
    """Fatia 19b: setViewMode(IconMode) liga Movement.Free por padrão, e em
    Free o Qt guarda a posição de cada ícone arrastado — era por isso que o
    card ficava preso onde o mouse soltava. A grade é sempre ordenada pela
    consulta, então tem que ser Static.

    (Trava a CONFIGURAÇÃO. Um teste do comportamento — simular o drop e
    comparar visualRect — não é possível: o filterDropEvent do Qt exige um
    QDrag real como event.source() e derruba o processo se for forjado.)
    """
    from PySide6.QtWidgets import QListView

    view, _modelo, _conn = grid
    assert view.movement() == QListView.Movement.Static
    # e o arrasto PARA FORA (tag, coleção, Blender) segue habilitado
    assert view.dragEnabled()


def test_restaurar_selecao_sozinho_jogaria_a_lista_para_o_item(grid, qapp):
    """A CAUSA do incômodo: setCurrentIndex rola a view até o item.

    Recarregar limpa a seleção; ao restaurá-la, a view salta. Por isso a
    barra tem de ser reposta DEPOIS da seleção — é o que _reload_grid faz.
    """
    view, modelo, _conn = grid
    barra = view.verticalScrollBar()
    barra.setValue(barra.maximum())
    qapp.processEvents()
    assert barra.value() > 0, "o teste precisa de uma lista rolável"

    modelo.reload()
    view.setCurrentIndex(modelo.index(0))  # sem repor a barra depois
    qapp.processEvents()

    assert barra.value() == 0  # saltou para o topo


def test_ordem_correta_preserva_posicao_e_selecao(grid, qapp):
    """O procedimento de MainWindow._reload_grid, na ordem certa."""
    view, modelo, _conn = grid
    barra = view.verticalScrollBar()
    barra.setValue(barra.maximum())
    qapp.processEvents()
    posicao = barra.value()

    alvo = modelo.row_at(modelo.index(40))
    view.setCurrentIndex(modelo.index(40))
    qapp.processEvents()

    guardado = barra.value()
    modelo.reload()
    idx = modelo.index_of_asset(alvo["id"])
    if idx is not None:
        view.setCurrentIndex(idx)
    barra.setValue(min(guardado, barra.maximum()))  # barra por ÚLTIMO
    qapp.processEvents()

    assert barra.value() == guardado
    assert modelo.row_at(view.currentIndex())["id"] == alvo["id"]
    assert posicao > 0
