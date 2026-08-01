"""dHash (Fatia 20): mesma textura em tamanhos diferentes bate; diferentes não."""

from PIL import Image

from assetdeck.thumbs.phash import compute_phash


def _salvar_gradiente(path, size):
    """Gradiente diagonal — dá um dHash não-trivial (não é tudo preto/branco)."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            v = int(255 * (x + y) / (size[0] + size[1]))
            px[x, y] = (v, v, v)
    img.save(path)


def _salvar_gradiente_invertido(path, size):
    """Mesma ideia do gradiente, mas decrescente — precisa sobreviver à
    redução pra 9x8 do dHash, então usa estrutura em larga escala (um
    xadrez fino se apaga na reamostragem e não serve de contraste)."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            v = 255 - int(255 * (x + y) / (size[0] + size[1]))
            px[x, y] = (v, v, v)
    img.save(path)


def test_mesma_imagem_em_tamanhos_diferentes_da_o_mesmo_phash(tmp_path):
    p1 = tmp_path / "grad_512.jpg"
    p2 = tmp_path / "grad_2048.jpg"
    _salvar_gradiente(p1, (512, 512))
    _salvar_gradiente(p2, (2048, 2048))

    assert compute_phash(p1) == compute_phash(p2)


def test_imagens_visualmente_diferentes_dao_phash_diferente(tmp_path):
    p1 = tmp_path / "grad.jpg"
    p2 = tmp_path / "grad_invertido.jpg"
    _salvar_gradiente(p1, (512, 512))
    _salvar_gradiente_invertido(p2, (512, 512))

    assert compute_phash(p1) != compute_phash(p2)


def test_arquivo_nao_raster_devolve_none(tmp_path):
    p = tmp_path / "modelo.blend"
    p.write_bytes(b"nao e uma imagem")

    assert compute_phash(p) is None


def test_arquivo_ilegivel_devolve_none_sem_erro(tmp_path):
    p = tmp_path / "corrompido.jpg"
    p.write_bytes(b"nao e um jpg de verdade")

    assert compute_phash(p) is None
