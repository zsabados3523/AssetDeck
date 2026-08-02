"""O primeiro QStyledItemDelegate do projeto (F4, Fatia 27).

Contrato que não pode mudar: sizeHint()==CELL, e o resto da configuração da
view (Static/SinglePass/uniformItemSizes) é responsabilidade de
test_grid_state.py, que continua rodando sem alteração nenhuma — é o teste de
regressão desta fatia.
"""

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui import asset_grid
from assetdeck.ui.asset_card_delegate import CELL, AssetCardDelegate


@pytest.fixture
def grid(qapp, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "foto.jpg")     # tem miniatura
    (root / "perfil.cube").write_text("LUT_3D_SIZE 2")     # não tem

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    pipeline = ThumbnailPipeline(tmp_path / "thumbs")
    modelo = asset_grid.AssetGridModel(conn, root, pipeline)
    view = asset_grid.AssetGridView()
    view.setModel(modelo)
    view.resize(400, 300)
    modelo.reload()
    view.show()
    qapp.processEvents()
    yield view, modelo, conn
    pipeline.shutdown()
    view.close()
    conn.close()


def _asset_id(conn, nome: str) -> int:
    row = conn.execute(
        "SELECT id FROM assets WHERE name = ? AND deleted_at IS NULL", (nome,)
    ).fetchone()
    assert row is not None, f"asset '{nome}' não foi indexado"
    return row["id"]


def test_view_usa_o_delegate_novo(grid):
    view, _modelo, _conn = grid
    assert isinstance(view.itemDelegate(), AssetCardDelegate)


def test_size_hint_e_exatamente_cell(grid):
    from PySide6.QtWidgets import QStyleOptionViewItem

    view, modelo, _conn = grid
    delegate = view.itemDelegate()
    option = QStyleOptionViewItem()
    option.initFrom(view)
    tam = delegate.sizeHint(option, modelo.index(0))
    assert (tam.width(), tam.height()) == (CELL.width(), CELL.height())


def test_display_role_nao_tem_prefixo_de_estrela_ou_oculto(grid):
    """O que saiu do DisplayRole (Fatia 27): a estrela e o "[oculto]" viram
    papéis próprios, desenhados como badge — não mais texto colado no nome."""
    _view, modelo, conn = grid
    aid = _asset_id(conn, "foto")
    assets_repo.set_starred(conn, aid, True)
    modelo.reload()

    idx = modelo.index_of_asset(aid)
    nome = modelo.data(idx, Qt.ItemDataRole.DisplayRole)
    assert nome == "foto"
    assert "★" not in nome and "[oculto]" not in nome


def test_papeis_novos_refletem_o_asset(grid):
    _view, modelo, conn = grid
    aid = _asset_id(conn, "foto")
    assets_repo.set_starred(conn, aid, True)
    assets_repo.set_hidden(conn, aid, True)
    # "Mostrar ocultos" precisa estar ligado, senão o asset oculto some da
    # grade e index_of_asset devolve None — comportamento correto do filtro,
    # não bug; o teste só quer ver o PAPEL, então liga o filtro pra achá-lo.
    modelo.set_filters(include_hidden=True)

    idx = modelo.index_of_asset(aid)
    assert modelo.data(idx, asset_grid.STARRED_ROLE) is True
    assert modelo.data(idx, asset_grid.HIDDEN_ROLE) is True
    assert modelo.data(idx, asset_grid.EXT_ROLE) == ".JPG"
    assert modelo.data(idx, Qt.ItemDataRole.ToolTipRole) is not None


def test_sem_miniatura_mostra_pastilha_e_chip_da_extensao(grid):
    """.cube não tem preview visual — HAS_THUMB_ROLE tem de ser False, e o
    EXT_ROLE é quem carrega o reconhecimento do tipo (chip), não mais cor."""
    _view, modelo, conn = grid
    aid = _asset_id(conn, "perfil")
    idx = modelo.index_of_asset(aid)

    assert modelo.data(idx, asset_grid.HAS_THUMB_ROLE) is False
    assert modelo.data(idx, asset_grid.EXT_ROLE) == ".CUBE"


def test_paint_nao_quebra_para_nenhuma_combinacao_de_estado(grid, qapp):
    """Roda paint() de verdade (não só monta os dados) para pegar erro de
    QPainter que só aparece na hora de desenhar — normal, favoritado, oculto
    e sem miniatura, e também com a linha SELECIONADA."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    view, modelo, conn = grid
    aid = _asset_id(conn, "foto")
    assets_repo.set_starred(conn, aid, True)
    assets_repo.set_hidden(conn, aid, True)
    modelo.set_filters(include_hidden=True)  # senão o oculto some da grade
    view.selectionModel().select(
        modelo.index(0),
        view.selectionModel().SelectionFlag.ClearAndSelect,
    )
    qapp.processEvents()

    delegate = view.itemDelegate()
    alvo = QPixmap(CELL)
    alvo.fill()
    painter = QPainter(alvo)
    try:
        for row in range(modelo.rowCount()):
            idx = modelo.index(row)
            option = QStyleOptionViewItem()
            option.initFrom(view)
            option.rect = QRect(0, 0, CELL.width(), CELL.height())
            if view.selectionModel().isSelected(idx):
                option.state |= QStyle.StateFlag.State_Selected
            delegate.paint(painter, option, idx)  # não pode levantar exceção
    finally:
        painter.end()


def test_set_icon_size_mantem_view_modelo_e_delegate_sincronizados(grid):
    """Slider de tamanho (Fatia 28): os três têm de mudar JUNTOS — foi
    exatamente a falta dessa sincronia que fazia a miniatura vazar por cima
    do nome."""
    view, modelo, _conn = grid
    view.set_icon_size(220)

    esperado = asset_grid.cell_for_icon(220)
    assert modelo._icon_px == 220
    assert view.itemDelegate()._cell == esperado
    assert view.iconSize().width() == 220
    assert view.gridSize() == esperado


def test_set_icon_size_respeita_os_limites(grid):
    view, _modelo, _conn = grid
    view.set_icon_size(9999)
    assert view.iconSize().width() == asset_grid.MAX_ICON
    view.set_icon_size(1)
    assert view.iconSize().width() == asset_grid.MIN_ICON


@pytest.mark.parametrize("px", [asset_grid.MIN_ICON, 160, asset_grid.MAX_ICON])
def test_pixmap_nunca_ultrapassa_o_tamanho_pedido(grid, px):
    """Regressão do bug relatado pelo Rafael: miniaturas vazando por cima do
    texto. A miniatura escalada pelo modelo tem de caber no quadrado que o
    delegate desenha, em qualquer tamanho do slider."""
    view, modelo, _conn = grid
    view.set_icon_size(px)
    for row in range(modelo.rowCount()):
        pix = modelo.data(modelo.index(row), Qt.ItemDataRole.DecorationRole)
        if pix is not None and not pix.isNull():
            assert pix.width() <= px
            assert pix.height() <= px
