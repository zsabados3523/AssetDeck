"""HDR/EXR: tonemap e thumbnail (arquivo .hdr sintético via OpenCV)."""

import numpy as np
import pytest
from PIL import Image

from assetdeck.thumbs.hdr import _read_exr, _tonemap, can_hdr, load_tonemapped
from assetdeck.thumbs.preview import can_preview, make_any_thumbnail
from pathlib import Path


def _write_hdr(path, array_rgb: np.ndarray) -> None:
    import cv2

    ok = cv2.imwrite(str(path), array_rgb[..., ::-1].astype(np.float32))  # RGB→BGR
    assert ok, "cv2 não conseguiu escrever o .hdr de teste"


def _write_exr_canais(path, canais: dict) -> None:
    import OpenEXR

    part = OpenEXR.Part({}, {nome: v.astype(np.float32) for nome, v in canais.items()})
    OpenEXR.File([part]).write(str(path))


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


@pytest.mark.parametrize("nome_canal", ["R", "G", "Y"])
def test_exr_canal_unico_vira_escala_de_cinza(tmp_path, nome_canal):
    # Mapas de displacement/roughness/altura frequentemente têm 1 canal só
    # (visto na biblioteca real: 'R', 'G' ou 'Y' sozinho, sem RGB completo).
    src = tmp_path / f"displacement_{nome_canal}.exr"
    valores = np.linspace(0.0, 2.0, 4 * 6, dtype=np.float32).reshape(4, 6)
    _write_exr_canais(src, {nome_canal: valores})

    rgb = _read_exr(src)

    assert rgb.shape == (4, 6, 3)
    assert np.array_equal(rgb[..., 0], rgb[..., 1])
    assert np.array_equal(rgb[..., 1], rgb[..., 2])
    assert np.allclose(rgb[..., 0], valores)


def test_exr_canal_unico_gera_thumbnail_de_ponta_a_ponta(tmp_path):
    src = tmp_path / "displacement.exr"
    valores = np.linspace(0.0, 2.0, 32 * 32, dtype=np.float32).reshape(32, 32)
    _write_exr_canais(src, {"R": valores})
    dest = tmp_path / "thumb.png"

    make_any_thumbnail(src, dest, size=16)

    with Image.open(dest) as t:
        assert t.mode == "RGB"
        assert max(t.size) == 16


def test_exr_canais_incompletos_ainda_levanta_erro(tmp_path):
    # 2 canais sem RGB/RGBA completo e sem ser o caso especial de 1 canal:
    # continua sendo um erro real, não deve virar thumbnail silenciosamente.
    src = tmp_path / "estranho.exr"
    _write_exr_canais(
        src,
        {"R": np.zeros((4, 4), np.float32), "X": np.zeros((4, 4), np.float32)},
    )

    with pytest.raises(ValueError):
        _read_exr(src)
