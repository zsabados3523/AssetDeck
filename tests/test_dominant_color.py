"""Cor média (Fatia 39): cor sólida bate exata; não-raster/corrompido dá None."""

from PIL import Image

from assetdeck.thumbs.dominant_color import compute_dominant_color


def _salvar_solida(path, cor, size=(64, 64)):
    Image.new("RGB", size, cor).save(path)


def test_cor_solida_da_a_propria_cor(tmp_path):
    p = tmp_path / "vermelho.png"
    _salvar_solida(p, (200, 30, 30))

    assert compute_dominant_color(p) == "#c81e1e"


def test_metade_preta_metade_branca_da_cinza_medio(tmp_path):
    p = tmp_path / "meio_a_meio.png"
    img = Image.new("RGB", (64, 64))
    px = img.load()
    for x in range(64):
        for y in range(64):
            px[x, y] = (255, 255, 255) if x < 32 else (0, 0, 0)
    img.save(p)

    assert compute_dominant_color(p) == "#808080"


def test_arquivo_nao_raster_devolve_none(tmp_path):
    p = tmp_path / "modelo.blend"
    p.write_bytes(b"nao e uma imagem")

    assert compute_dominant_color(p) is None


def test_arquivo_ilegivel_devolve_none_sem_erro(tmp_path):
    p = tmp_path / "corrompido.jpg"
    p.write_bytes(b"nao e um jpg de verdade")

    assert compute_dominant_color(p) is None
