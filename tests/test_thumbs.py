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


def test_png_paletado_com_transparencia_nao_pinta_cor_da_paleta(tmp_path):
    """Bug relatado pelo Rafael (Fatia 58): previews assinalados
    automaticamente apareciam com manchas verdes ALEATÓRIAS na grade, mas
    normais no preview grande do painel de detalhes.

    Causa: uma imagem em modo 'P' com um índice de paleta marcado
    transparente (`tRNS`) não tem banda 'A' em `getbands()` — caía direto
    no `.convert("RGB")`, que ignora a transparência e pinta o pixel com a
    cor CRUA daquele índice (por isso "aleatório": depende de qual cor
    cada arquivo tinha ali). O painel de detalhes nunca teve o bug porque
    carrega o arquivo direto via Qt (`QPixmap`), não por aqui."""
    src = tmp_path / "paleta_transparente.png"
    img = Image.new("P", (32, 32), color=0)
    paleta = [0, 0, 0] * 256
    paleta[0:3] = [255, 0, 255]  # índice 0: cor "lixo" do slot transparente
    paleta[3:6] = [200, 60, 60]  # índice 1: conteúdo real (opaco)
    img.putpalette(paleta)
    px = img.load()
    for y in range(32):
        for x in range(32):
            px[x, y] = 1 if 10 <= x < 22 and 10 <= y < 22 else 0
    img.info["transparency"] = 0
    img.save(src)
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest)

    with Image.open(dest) as t:
        assert t.mode == "RGBA"
        # canto (índice 0, "transparente"): alpha zero, não a cor da paleta
        assert t.getpixel((2, 2))[3] == 0
        # miolo (índice 1, conteúdo real): continua opaco e com a cor certa
        assert t.getpixel((16, 16)) == (200, 60, 60, 255)


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


@pytest.mark.parametrize("mode", ["1", "P", "CMYK", "L", "RGB"])
def test_tif_em_varios_modos_de_cor_gera_thumbnail(tmp_path, mode):
    """Fatia 42: 163 `.tif` ("Silhuetas", tipicamente máscaras 1-bit/paleta)
    ficavam sem thumbnail na biblioteca real. `_to_safe_mode` agora
    converte o modo ANTES do resize (não depois) — cobre qualquer modo
    exótico, não só os que apareceram na testlib.

    Nesta versão do Pillow (12.3.1) nenhum desses modos falha na ordem
    ANTIGA (testado à parte) — não dá pra provar red→green sem os
    arquivos reais do Rafael. Fica como cobertura de regressão."""
    src = tmp_path / f"silhueta_{mode}.tif"
    Image.new(mode, (300, 200)).save(src)
    dest = tmp_path / "thumb.png"

    make_thumbnail(src, dest)

    assert dest.exists()
    with Image.open(dest) as t:
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
