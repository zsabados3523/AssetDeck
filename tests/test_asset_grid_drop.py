"""Fatia 44 (investigação): cobertura que faltava — um QDropEvent DE
VERDADE (não só chamar o handler direto) contra a AssetGridView, com
hasUrls() real. Isolado da hipótese de integração XDND do SO (fora do que
dá pra testar headless) — isto só prova que a lógica Python em si
(dragEnterEvent/dropEvent/_dropped_image) reage certo a um evento genuíno
do Qt, reforçando a suspeita de que o bug relatado pelo Rafael é do
gerenciador de arquivos ↔ Qt, não do código do app.
"""

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import MIME_ASSETS, AssetGridModel, AssetGridView


@pytest.fixture
def grid(qapp, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "modelo.png")
    (root / "cena.blend").write_bytes(b"blend" * 20)  # asset sem preview nativo
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
    yield view, modelo, conn, tmp_path
    pipeline.shutdown()
    view.close()
    conn.close()


def _card_center(view, modelo, nome_asset):
    linha = next(
        modelo.row_at(modelo.index(i)) for i in range(modelo.rowCount())
        if modelo.row_at(modelo.index(i))["name"] == nome_asset
    )
    idx = modelo.index_of_asset(linha["id"])
    return view.visualRect(idx).center(), linha["id"]


def _drop_event(pos, mime):
    return QDropEvent(QPointF(pos), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def _drag_enter_event(pos, mime):
    return QDragEnterEvent(pos, Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_drag_enter_com_imagem_externa_e_aceito(grid, tmp_path):
    view, modelo, _conn, _tmp = grid
    externo = tmp_path / "externa.jpg"
    externo.write_bytes(b"j" * 20)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(externo))])

    pos, _asset_id = _card_center(view, modelo, "modelo")
    event = _drag_enter_event(pos, mime)
    view.dragEnterEvent(event)

    assert event.isAccepted()


def test_drop_de_imagem_externa_emite_image_dropped(grid, tmp_path):
    """O caso relatado pelo Rafael: soltar um .jpg/.png do gerenciador de
    arquivos do sistema sobre um card sem preview nativo (.blend) devia
    definir a imagem como capa (Fatia 10)."""
    view, modelo, _conn, _tmp = grid
    externo = tmp_path / "externa.png"
    externo.write_bytes(b"p" * 20)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(externo))])

    pos, asset_id = _card_center(view, modelo, "cena")
    recebido = []
    view.image_dropped.connect(lambda aid, path: recebido.append((aid, path)))

    event = _drop_event(pos, mime)
    view.dropEvent(event)

    assert event.isAccepted()
    assert recebido == [(asset_id, str(externo))]


def test_drop_de_extensao_nao_raster_e_ignorado(grid, tmp_path):
    view, modelo, _conn, _tmp = grid
    externo = tmp_path / "leiame.txt"
    externo.write_text("nao e imagem")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(externo))])

    pos, _asset_id = _card_center(view, modelo, "modelo")
    recebido = []
    view.image_dropped.connect(lambda aid, path: recebido.append((aid, path)))

    event = _drop_event(pos, mime)
    view.dropEvent(event)

    assert not event.isAccepted()
    assert recebido == []


def test_drop_interno_mime_assets_nao_e_tratado_como_imagem_externa(grid):
    """Arrastar um asset de dentro da própria grid usa MIME_ASSETS — mesmo
    que o mime também tivesse hasUrls(), não pode virar 'preview externo'
    (Fatia 10b: esse caso é asset_preview_dropped, não image_dropped)."""
    view, modelo, _conn, _tmp = grid
    pos_origem, origem_id = _card_center(view, modelo, "modelo")
    pos_alvo, alvo_id = _card_center(view, modelo, "cena")

    mime = QMimeData()
    mime.setData(MIME_ASSETS, str(origem_id).encode())

    recebido_imagem = []
    recebido_asset = []
    view.image_dropped.connect(lambda aid, path: recebido_imagem.append((aid, path)))
    view.asset_preview_dropped.connect(lambda aid, origens: recebido_asset.append((aid, origens)))

    event = _drop_event(pos_alvo, mime)
    view.dropEvent(event)

    assert event.isAccepted()
    assert recebido_imagem == []
    assert recebido_asset == [(alvo_id, [origem_id])]
