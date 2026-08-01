"""Thumbnails: geração, proporção, alpha, cache e erros legíveis."""

from pathlib import Path

import pytest
from PIL import Image

from assetdeck.thumbs.cache import thumb_path
from assetdeck.thumbs.raster import can_thumbnail, make_thumbnail


def _make_image(path: Path, size=(1024, 512), mode="RGB", color=(200, 30, 30)):
    Image.new(mode, size, color).save(path)


def test_can_thumbnail_por_extensao():
    assert can_thumbnail(Path("x.jpg"))
    assert can_thumbnail(Path("x.TIF"))
    assert not can_thumbnail(Path("x.exr"))   # Fatia 7
    assert not can_thumbnail(Path("x.blend"))


def test_thumbnail_respeita_tamanho_e_proporcao(tmp_path):
    src = tmp_path / "grande.jpg"
    _make_image(src, size=(1024, 512))
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest, size=256)

    with Image.open(dest) as t:
        assert t.width == 256
        assert t.height == 128  # proporção 2:1 mantida


def test_imagem_menor_que_a_thumb_nao_e_ampliada(tmp_path):
    src = tmp_path / "pequena.png"
    _make_image(src, size=(100, 80))
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest, size=256)

    with Image.open(dest) as t:
        assert (t.width, t.height) == (100, 80)


def test_png_com_alpha_mantem_transparencia_real(tmp_path):
    """Cutout: transparência REAL na thumb — o fundo do app aparece por trás
    (Fatia 8, feedback do Rafael; o xadrez da v2 foi descartado)."""
    src = tmp_path / "cutout.png"
    Image.new("RGBA", (400, 400), (0, 128, 0, 100)).save(src)
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest)

    with Image.open(dest) as t:
        assert t.mode == "RGBA"
        assert t.getpixel((5, 5))[3] == 100  # canal alpha intacto


def test_modo_exotico_e_convertido(tmp_path):
    src = tmp_path / "paleta.png"
    Image.new("P", (300, 300)).save(src)  # imagem com paleta
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest)
    assert dest.exists()


def test_arquivo_corrompido_levanta_erro_e_nao_deixa_lixo(tmp_path):
    src = tmp_path / "quebrada.jpg"
    src.write_bytes(b"isto nao e um jpeg")
    dest = tmp_path / "thumb.png"

    with pytest.raises(Exception):
        make_thumbnail(src, dest)
    assert not dest.exists()  # escrita atômica: nada pela metade no cache


def test_png_com_chunk_iccp_corrompido_e_resgatado(tmp_path):
    """Packs de assets circulam com iCCP de CRC inválido; o resgate em memória
    deve abrir mesmo assim — sem jamais alterar o arquivo original."""
    src = tmp_path / "pack.png"
    _make_image(src, size=(300, 200))
    dados = bytearray(src.read_bytes())

    # Injeta um chunk acessório 'iCCP' com CRC propositalmente errado após o IHDR
    fim_ihdr = 8 + 12 + 13  # assinatura + chunk IHDR completo
    ruim = (b"\x00\x00\x00\x04" + b"iCCP" + b"lixo" + b"\x00\x00\x00\x00")
    corrompido = bytes(dados[:fim_ihdr]) + ruim + bytes(dados[fim_ihdr:])
    src.write_bytes(corrompido)

    import pytest as _pytest
    from PIL import Image as _Image

    with _pytest.raises(Exception):
        _Image.open(src).load()  # Pillow puro recusa…

    dest = tmp_path / "thumb.png"
    make_thumbnail(src, dest)   # …o resgate abre e gera a thumb
    assert dest.exists()
    assert src.read_bytes() == corrompido  # original INTOCADO (somente-leitura)


def test_16bit_grayscale_e_suportado(tmp_path):
    """Mapas de displacement/roughness vêm em 16-bit (modo I;16)."""
    src = tmp_path / "height.png"
    Image.new("I;16", (512, 512), 30000).save(src)
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest)

    with Image.open(dest) as t:
        assert t.mode == "L"
        assert t.width == 256


def test_geracao_concorrente_do_mesmo_destino_nao_quebra(tmp_path):
    """Packs diferentes com o MESMO arquivo → mesmo hash → mesmo destino.
    Oito threads gerando a mesma thumb ao mesmo tempo não podem se atropelar."""
    from concurrent.futures import ThreadPoolExecutor

    src = tmp_path / "dup.jpg"
    _make_image(src, size=(800, 800))
    dest = tmp_path / "thumb.png"

    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in [pool.submit(make_thumbnail, src, dest) for _ in range(8)]:
            f.result()  # qualquer exceção estoura aqui

    assert dest.exists()
    assert not list(tmp_path.glob("*.tmp"))  # nenhum resto pela metade


def test_thumb_path_e_deterministico(tmp_path):
    a = thumb_path(tmp_path, "abc123")
    b = thumb_path(tmp_path, "abc123")
    c = thumb_path(tmp_path, "outrohash")
    assert a == b
    assert a != c
    assert a.suffix == ".png"
