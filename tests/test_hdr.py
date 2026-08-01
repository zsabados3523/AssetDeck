"""HDR/EXR: tonemap e thumbnail (arquivo .hdr sintético via OpenCV)."""

import numpy as np
import pytest
from PIL import Image

from assetdeck.thumbs.hdr import _tonemap, can_hdr, load_tonemapped
from assetdeck.thumbs.preview import can_preview, make_any_thumbnail
from pathlib import Path


def _write_hdr(path, array_rgb: np.ndarray) -> None:
    import cv2

    ok = cv2.imwrite(str(path), array_rgb[..., ::-1].astype(np.float32))  # RGB→BGR
    assert ok, "cv2 não conseguiu escrever o .hdr de teste"


def test_can_hdr_e_can_preview():
    assert can_hdr(Path("x.hdr")) and can_hdr(Path("x.EXR"))
    assert not can_hdr(Path("x.jpg"))
    assert can_preview(Path("x.hdr")) and can_preview(Path("x.jpg"))
    assert not can_preview(Path("x.blend"))


def test_tonemap_comprime_alcance_dinamico():
    # Sol de 5000x de intensidade + sombra: ambos precisam caber em 0..255
    rgb = np.zeros((4, 4, 3), np.float32)
    rgb[0, 0] = 5000.0   # "sol"
    rgb[2, 2] = 0.05     # "sombra"
    out = _tonemap(rgb)
    assert out.dtype == np.uint8
    assert out[0, 0, 0] > 200        # sol: claro, mas não infinito
    assert 0 <= out[2, 2, 0] < 255   # sombra: não estourou


def test_tonemap_sobrevive_a_nan_e_infinito():
    rgb = np.full((2, 2, 3), np.nan, np.float32)
    rgb[0, 0] = np.inf
    out = _tonemap(rgb)  # não pode levantar
    assert out.shape == (2, 2, 3)


def test_hdr_real_vira_thumbnail(tmp_path):
    src = tmp_path / "ceu.hdr"
    gradiente = np.linspace(0.01, 800.0, 64 * 32 * 3, dtype=np.float32)
    _write_hdr(src, gradiente.reshape(32, 64, 3))
    dest = tmp_path / "thumb.png"

    make_any_thumbnail(src, dest, size=32)

    with Image.open(dest) as t:
        assert t.mode == "RGB"
        assert max(t.size) == 32


def test_load_tonemapped_resolucao_completa(tmp_path):
    src = tmp_path / "amplo.hdr"
    _write_hdr(src, np.full((40, 80, 3), 2.5, np.float32))
    img = load_tonemapped(src)
    assert (img.width, img.height) == (80, 40)  # resolução original preservada


def test_hdr_ilegivel_levanta_erro(tmp_path):
    ruim = tmp_path / "falso.hdr"
    ruim.write_bytes(b"nao sou radiance")
    with pytest.raises(ValueError):
        load_tonemapped(ruim)
