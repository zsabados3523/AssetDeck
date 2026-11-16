"""Falhas de thumbnail lembradas entre sessões (Issue #31)."""

from PIL import Image

from assetdeck.thumbs import pipeline as pipe
from assetdeck.thumbs.cache import falha_path, thumb_path
from assetdeck.thumbs.pipeline import ThumbnailPipeline


def _pipeline(tmp_path, qapp):
    return ThumbnailPipeline(tmp_path / "thumbs")


def test_falha_de_decoder_vira_marcador_e_nao_e_tentada_de_novo(tmp_path, qapp):
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    ruim = tmp_path / "ruim.png"
    ruim.write_bytes(b"isto nao e uma imagem")

    p = _pipeline(tmp_path, qapp)
    assert p.warmup([(1, ruim, "h1")]) == 1
    p._pool.waitForDone(10000)
    qapp.processEvents()

    assert falha_path(thumbs, "h1").read_text(encoding="utf-8") == pipe._versao_pillow()

    # Nova sessão: nada é agendado, nem pelo warmup nem sob demanda.
    p2 = _pipeline(tmp_path, qapp)
    assert p2.warmup([(1, ruim, "h1")]) == 0
    assert p2.get_or_request(1, ruim, "h1") is None
    assert 1 not in p2._inflight


def test_arquivo_ausente_nao_vira_marcador(tmp_path, qapp):
    """Rede fora do ar ou arquivo movido é passageiro: tenta de novo depois."""
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    sumido = tmp_path / "nao_existe.png"

    p = _pipeline(tmp_path, qapp)
    assert p.warmup([(2, sumido, "h2")]) == 1
    p._pool.waitForDone(10000)
    qapp.processEvents()

    assert not falha_path(thumbs, "h2").exists()
    assert _pipeline(tmp_path, qapp).warmup([(2, sumido, "h2")]) == 1


def test_marcador_de_outra_versao_do_pillow_e_ignorado(tmp_path, qapp, monkeypatch):
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    boa = tmp_path / "boa.png"
    Image.new("RGB", (8, 8)).save(boa)
    falha_path(thumbs, "h3").write_text("0.0.0-antiga", encoding="utf-8")

    p = _pipeline(tmp_path, qapp)
    assert p.warmup([(3, boa, "h3")]) == 1
    p._pool.waitForDone(10000)
    qapp.processEvents()
    assert thumb_path(thumbs, "h3").is_file()
