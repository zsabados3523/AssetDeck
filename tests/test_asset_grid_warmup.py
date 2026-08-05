"""Bug de performance achado em 2026-08-05 (Rafael, biblioteca real de
23 mil assets): `reload()` chamava `_warmup()`, que varre a biblioteca
INTEIRA sem filtro (72 mil linhas no modo expandido pra ele) e confere no
disco se cada thumbnail já existe — medido em ~1,1s, rodando no thread
principal, TRAVANDO A UI. E `reload()` é chamado a cada drop de preview,
favorito, nota, toggle de tag… ações que deveriam ser instantâneas.

Fix: `reload()` virou barato (só `_requery()`); o pré-aquecimento saiu pra
`warmup_library()`, chamada só onde arquivo novo pode ter aparecido
(varredura, rename em lote, agrupar/desagrupar) — não a cada mudancinha.
"""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel


@pytest.fixture
def modelo(qapp, tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    for i in range(5):
        Image.new("RGB", (32, 32)).save(root / f"asset_{i}.jpg")
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    pipeline = ThumbnailPipeline(tmp_path / "thumbs")
    m = AssetGridModel(conn, root, pipeline)
    yield m
    pipeline.shutdown()
    conn.close()


def test_reload_nao_chama_warmup(modelo, monkeypatch):
    """O caso que causava a trava: qualquer ação que só precisa reler os
    dados (definir preview, favoritar, taggear) usa reload() — e reload()
    NÃO pode mais varrer a biblioteca inteira em busca de thumbnails."""
    chamadas = []
    monkeypatch.setattr(modelo._pipeline, "warmup", lambda items: chamadas.append(items))

    modelo.reload()

    assert chamadas == [], "reload() não pode chamar warmup() — é o bug da lentidão"
    assert modelo.rowCount() == 5, "mas a consulta (_requery) precisa continuar rodando"


def test_warmup_library_chama_warmup(modelo, monkeypatch):
    """O caso que PRECISA continuar existindo: depois de uma varredura de
    verdade, o pré-aquecimento tem que rodar (arquivo novo pode ter
    chegado) — só que agora por um método explícito, não pelo reload()."""
    chamadas = []
    monkeypatch.setattr(modelo._pipeline, "warmup", lambda items: chamadas.append(items))

    modelo.warmup_library()

    assert len(chamadas) == 1
    assert len(chamadas[0]) == 5  # os 5 .jpg do fixture, todos previewable
    assert modelo.rowCount() == 5  # e a consulta também rodou


def test_reload_e_warmup_library_concordam_nos_dados(modelo):
    """Os dois precisam continuar refletindo os mesmos filtros/estado —
    a diferença é só se o pré-aquecimento roda junto ou não."""
    modelo.reload()
    linhas_reload = modelo.rowCount()

    modelo.warmup_library()
    linhas_warmup = modelo.rowCount()

    assert linhas_reload == linhas_warmup == 5
