"""Trabalho de fundo não pode engasgar o que o usuário está esperando ver.

Regressão do relato do Rafael em 2026-08-19: "ao clicar duas vezes num
.blend ou num .hdr nada abre". A janela até abria, mas em "Carregando…"
pra sempre — a carga entrava no MESMO `QThreadPool.globalInstance()` das
miniaturas, atrás de centenas de jobs (e as células visíveis da grade
ainda entram com prioridade 1, furando a fila). Com a varredura da
biblioteca real rodando junto, a fila nunca esvaziava.
"""

import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QRunnable, QThreadPool

from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui import hdri_viewer, model_viewer, pools


class _JobQueTrava(QRunnable):
    """Ocupa uma thread até o teste soltar."""

    def __init__(self, solta: threading.Event) -> None:
        super().__init__()
        self._solta = solta

    def run(self) -> None:
        self._solta.wait(timeout=30)


@pytest.fixture
def pool_global_entupido():
    """Enche TODAS as threads do pool global e mais um tanto na fila."""
    solta = threading.Event()
    glob = QThreadPool.globalInstance()
    for _ in range(glob.maxThreadCount() + 20):
        glob.start(_JobQueTrava(solta))
    yield
    solta.set()
    glob.waitForDone(30000)


def test_hdri_carrega_com_o_pool_global_entupido(qapp, tmp_path, pool_global_entupido):
    import cv2

    caminho = tmp_path / "ceu.hdr"
    hdr = np.zeros((8, 16, 3), np.float32)
    hdr[:4] = (2.0, 1.5, 1.0)
    assert cv2.imwrite(str(caminho), hdr)

    recebidos = []
    sig = hdri_viewer.SinalCarga()
    sig.loaded.connect(lambda img: recebidos.append(img))
    sig.failed.connect(lambda msg: recebidos.append(msg))

    hdri_viewer.iniciar_carga(sig, caminho)

    assert pools.interativo().waitForDone(10000), (
        "a carga do HDRI ficou presa — voltou a dividir fila com o trabalho "
        "de fundo?"
    )
    qapp.processEvents()
    assert len(recebidos) == 1


def test_modelo_carrega_com_o_pool_global_entupido(qapp, tmp_path, pool_global_entupido):
    caminho = tmp_path / "cubo.obj"
    caminho.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nvn 0 0 1\nf 1//1 2//1 3//1\n")

    recebidos = []
    sig = model_viewer.SinalCarga()
    sig.loaded.connect(lambda m: recebidos.append(m))
    sig.failed.connect(lambda msg: recebidos.append(msg))

    model_viewer.iniciar_carga(sig, caminho)

    assert pools.interativo().waitForDone(10000), (
        "a carga do modelo ficou presa — voltou a dividir fila com o "
        "trabalho de fundo?"
    )
    qapp.processEvents()
    assert len(recebidos) == 1


# ---- os pools são mesmo separados ----

def test_o_pool_interativo_nao_e_o_global(qapp):
    assert pools.interativo() is not QThreadPool.globalInstance()


def test_as_miniaturas_nao_usam_o_pool_global(qapp, tmp_path):
    """`shutdown()` chama `clear()` no próprio pool — no global, isso
    descartava de quebra o que o visualizador tivesse pendente."""
    pipeline = ThumbnailPipeline(tmp_path)
    assert pipeline._pool is not QThreadPool.globalInstance()
    assert pipeline._pool is not pools.interativo()


def test_as_miniaturas_deixam_nucleo_sobrando(qapp, tmp_path):
    """Com uma thread por núcleo, a abertura do app (que agenda centenas de
    miniaturas de uma vez) tomava a máquina inteira junto com os processos
    da varredura — o "uso de CPU sobe bastante" do relato."""
    import os

    pipeline = ThumbnailPipeline(tmp_path)
    nucleos = os.cpu_count() or 4
    assert pipeline._pool.maxThreadCount() <= max(2, nucleos // 2)
    assert pipeline._pool.maxThreadCount() >= 2


def test_uma_miniatura_lenta_nao_atrasa_o_visualizador(qapp, tmp_path):
    """O teste que junta tudo: fila de miniaturas cheia E o pool global
    ocupado, e mesmo assim a prévia do visualizador tem thread livre."""
    pipeline = ThumbnailPipeline(tmp_path)
    solta = threading.Event()
    try:
        for _ in range(pipeline._pool.maxThreadCount() + 10):
            pipeline._pool.start(_JobQueTrava(solta))

        caminho = tmp_path / "imagem.png"
        Image.new("RGB", (4, 4), (255, 0, 0)).save(caminho)

        livre = pools.interativo().tryStart(_JobQueTrava(threading.Event()))
        assert livre, "não sobrou thread interativa com as miniaturas cheias"
    finally:
        solta.set()
        pipeline._pool.clear()
        pipeline._pool.waitForDone(30000)
        pools.interativo().waitForDone(30000)


# ---- miniaturas rodam em segundo plano ----

def test_a_thread_de_miniatura_e_rebaixada_uma_vez_so(monkeypatch):
    """`nice` é CUMULATIVO: a mesma thread do pool atende muitos jobs, e sem
    a trava por thread cada job rebaixaria mais um degrau até o fundo."""
    from assetdeck.thumbs import pipeline

    chamadas = []
    monkeypatch.setattr(pipeline.os, "nice", lambda n: chamadas.append(n))
    monkeypatch.setattr(pipeline, "_rebaixada", threading.local())

    for _ in range(5):
        pipeline.rebaixar_esta_thread()

    assert chamadas == [5]


def test_cada_thread_e_rebaixada_por_conta_propria(monkeypatch):
    from assetdeck.thumbs import pipeline

    chamadas = []
    monkeypatch.setattr(pipeline.os, "nice", lambda n: chamadas.append(n))
    monkeypatch.setattr(pipeline, "_rebaixada", threading.local())

    outra = threading.Thread(target=pipeline.rebaixar_esta_thread)
    pipeline.rebaixar_esta_thread()
    outra.start()
    outra.join()

    assert chamadas == [5, 5]
