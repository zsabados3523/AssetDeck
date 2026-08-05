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
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QCursor, QDragEnterEvent, QDropEvent

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


# ---- Fatia 51: fallback por posição do cursor ----
#
# Log real do Rafael (2026-08-05, 5 tentativas): startDrag dispara e
# retorna, mas dragEnterEvent/dropEvent NUNCA chegam ao soltar um asset
# sobre OUTRO asset da MESMA grade — mesmo com outros arrastos (Tags,
# Coleções, Blender) funcionando normalmente. Isolado como específico de
# soltar DENTRO da própria view (não é XDND quebrado em geral).
#
# Fix: depois que a chamada nativa bloqueante (super().startDrag() ou
# drag.exec()) retorna, se dropEvent não confirmou entrega
# (_native_drop_handled ainda False), aplica o efeito a partir da posição
# REAL do cursor (QCursor.pos(), não sintética) — não depende da entrega
# nativa do evento a lugar nenhum.
#
# QTest.mouseMove NÃO move o QCursor.pos() real neste ambiente (confirmado
# ao investigar: o cursor ficou parado longe da posição simulada) — por
# isso estes testes MOCAM QCursor.pos() para exercer a lógica de forma
# determinística, em vez de tentar simular o drag nativo inteiro.

def test_dropEvent_marca_entrega_nativa_confirmada(grid):
    view, modelo, _conn, _tmp = grid
    pos_alvo, _alvo_id = _card_center(view, modelo, "cena")
    mime = QMimeData()
    mime.setData(MIME_ASSETS, b"1")

    assert view._native_drop_handled is False
    view.dropEvent(_drop_event(pos_alvo, mime))
    assert view._native_drop_handled is True


def test_fallback_aplica_asset_sobre_asset_pela_posicao_do_cursor(grid, monkeypatch):
    """O caso do bug: soltar sobre outro card SEM dropEvent nativo chegar —
    simulado aqui como 'nunca chamamos dropEvent', só o fallback."""
    view, modelo, _conn, _tmp = grid
    pos_alvo, alvo_id = _card_center(view, modelo, "cena")
    _pos_origem, origem_id = _card_center(view, modelo, "modelo")

    monkeypatch.setattr(QCursor, "pos", staticmethod(
        lambda: view.viewport().mapToGlobal(pos_alvo)
    ))

    recebido = []
    view.asset_preview_dropped.connect(lambda aid, origens: recebido.append((aid, origens)))

    mime = QMimeData()
    mime.setData(MIME_ASSETS, str(origem_id).encode())
    view._fallback_drop_by_cursor_position(mime, {origem_id})

    assert recebido == [(alvo_id, [origem_id])]


def test_fallback_ignora_quando_cursor_esta_sobre_a_propria_origem(grid, monkeypatch):
    """Soltar 'em cima de si mesmo' (o cursor não saiu do item de origem)
    não pode disparar nada — nem no caminho nativo, nem no fallback."""
    view, modelo, _conn, _tmp = grid
    pos_origem, origem_id = _card_center(view, modelo, "modelo")

    monkeypatch.setattr(QCursor, "pos", staticmethod(
        lambda: view.viewport().mapToGlobal(pos_origem)
    ))

    recebido = []
    view.asset_preview_dropped.connect(lambda aid, origens: recebido.append((aid, origens)))

    mime = QMimeData()
    mime.setData(MIME_ASSETS, str(origem_id).encode())
    view._fallback_drop_by_cursor_position(mime, {origem_id})

    assert recebido == []


def test_fallback_ignora_quando_cursor_esta_fora_da_grade(grid, monkeypatch):
    """Soltar em outro widget/janela (Blender, Tags, Coleções — que já
    funcionam pelo caminho nativo) não pode ser 'roubado' pelo fallback."""
    view, modelo, _conn, _tmp = grid
    _pos_origem, origem_id = _card_center(view, modelo, "modelo")

    # Bem fora dos limites da view — indexAt() retorna índice inválido.
    monkeypatch.setattr(QCursor, "pos", staticmethod(
        lambda: view.viewport().mapToGlobal(QPoint(-500, -500))
    ))

    recebido = []
    view.asset_preview_dropped.connect(lambda aid, origens: recebido.append((aid, origens)))
    view.image_dropped.connect(lambda aid, path: recebido.append((aid, path)))

    mime = QMimeData()
    mime.setData(MIME_ASSETS, str(origem_id).encode())
    view._fallback_drop_by_cursor_position(mime, {origem_id})

    assert recebido == []


def test_fallback_tambem_funciona_para_imagem_externa(grid, tmp_path, monkeypatch):
    """Mesma lógica vale para o caso irmão (Fatia 44: imagem do gerenciador
    de arquivos solta sobre um card) — um único fallback cobre os dois."""
    view, modelo, _conn, _tmp = grid
    pos_alvo, alvo_id = _card_center(view, modelo, "cena")
    externo = tmp_path / "externa.png"
    externo.write_bytes(b"p" * 20)

    monkeypatch.setattr(QCursor, "pos", staticmethod(
        lambda: view.viewport().mapToGlobal(pos_alvo)
    ))

    recebido = []
    view.image_dropped.connect(lambda aid, path: recebido.append((aid, path)))

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(externo))])
    view._fallback_drop_by_cursor_position(mime, set())

    assert recebido == [(alvo_id, str(externo))]


def test_apply_drop_retorna_false_sem_efeito_colateral_quando_nada_bate(grid):
    view, modelo, _conn, _tmp = grid
    _pos, alvo_row = _card_center(view, modelo, "cena")
    row = modelo.row_at(modelo.index_of_asset(alvo_row))

    mime = QMimeData()  # sem urls, sem MIME_ASSETS — mime "vazio"
    assert view._apply_drop(mime, row) is False
