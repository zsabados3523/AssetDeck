"""Busca FTS e filtros combinados de tipo/pasta/subpastas."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.folder_tree import list_dirs


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def lib(tmp_path, conn):
    """Biblioteca sintética com estrutura de pastas e nomes buscáveis."""
    root = tmp_path / "lib"
    (root / "Texturas" / "Concreto").mkdir(parents=True)
    (root / "Texturas" / "Madeira").mkdir(parents=True)
    (root / "HDRIs").mkdir()
    (root / "Texturas" / "Concreto" / "Concreto Rústico 4K.jpg").write_bytes(b"a" * 50)
    (root / "Texturas" / "Concreto" / "concrete_polished.png").write_bytes(b"b" * 50)
    (root / "Texturas" / "Madeira" / "Wood Oak.jpg").write_bytes(b"c" * 50)
    (root / "Texturas" / "na_raiz_texturas.jpg").write_bytes(b"d" * 50)
    (root / "HDRIs" / "studio_small.hdr").write_bytes(b"e" * 50)
    (root / "solto_na_raiz.png").write_bytes(b"f" * 50)
    # nome composto sem separador — o caso exato da limitação da Fatia 12
    (root / "Texturas" / "StoneQuartziteTile_2K.jpg").write_bytes(b"g" * 50)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)  # já reconstrói o FTS
    return root


def _names(rows):
    return sorted(r["name"] for r in rows)


def test_sem_filtro_traz_tudo(conn, lib):
    assert len(assets_repo.list_for_grid(conn)) == 7


def test_busca_por_prefixo(conn, lib):
    rows = assets_repo.list_for_grid(conn, search="conc")
    assert _names(rows) == ["Concreto Rústico 4K", "concrete_polished"]


def test_busca_ignora_acentos(conn, lib):
    rows = assets_repo.list_for_grid(conn, search="rustico")  # sem acento
    assert _names(rows) == ["Concreto Rústico 4K"]


def test_busca_multi_palavra_e_AND(conn, lib):
    assert _names(assets_repo.list_for_grid(conn, search="concreto 4k")) \
        == ["Concreto Rústico 4K"]
    assert assets_repo.list_for_grid(conn, search="concreto oak") == []


def test_busca_com_conector_e_explicito(conn, lib):
    assert _names(assets_repo.list_for_grid(conn, search="concreto E 4k")) \
        == ["Concreto Rústico 4K"]
    assert assets_repo.list_for_grid(conn, search="concreto E oak") == []


def test_busca_com_conector_ou(conn, lib):
    # "concreto" (com 'o') não bate com "concrete" (com 'e') — só o exato
    nomes = _names(assets_repo.list_for_grid(conn, search="concreto OU oak"))
    assert nomes == ["Concreto Rústico 4K", "Wood Oak"]


def test_busca_com_conector_nao(conn, lib):
    # "raiz" bate em na_raiz_texturas E solto_na_raiz; NÃO solto exclui o 2º
    nomes = _names(assets_repo.list_for_grid(conn, search="raiz NÃO solto"))
    assert nomes == ["na_raiz_texturas"]
    # sem acento no "não" também funciona
    nomes = _names(assets_repo.list_for_grid(conn, search="raiz nao solto"))
    assert nomes == ["na_raiz_texturas"]


def test_busca_acha_substring_em_nome_composto(conn, lib):
    """O critério da fatia — a limitação registrada na Fatia 12."""
    nomes = _names(assets_repo.list_for_grid(conn, search="quartzite"))
    assert nomes == ["StoneQuartziteTile_2K"]


def test_substring_nao_ativa_com_conector(conn, lib):
    # Com E/OU/NÃO a via de substring fica desligada (escopo desta fatia);
    # "stone" sozinho (sem conector) já acharia via substring, mas aqui
    # testamos que um conector não quebra nem gera resultado incorreto.
    assets_repo.list_for_grid(conn, search="stone E xyz123")  # não pode explodir


def test_conector_solto_nao_quebra_a_busca(conn, lib):
    for maldade in ["E", "OU", "NÃO", "E OU NÃO", "  e  "]:
        assets_repo.list_for_grid(conn, search=maldade)  # não pode levantar


def test_busca_com_caracteres_especiais_nao_explode(conn, lib):
    # Aspas, operadores FTS e curingas não podem virar erro de sintaxe
    for maldade in ['"', "AND OR NOT", "conc*", "a:b", "(x)", "   "]:
        assets_repo.list_for_grid(conn, search=maldade)  # não pode levantar


def test_filtro_por_tipo(conn, lib):
    rows = assets_repo.list_for_grid(conn, asset_types=["hdri"])
    assert _names(rows) == ["studio_small"]


def test_filtro_multi_tipo_em_checklist(conn, lib):
    # Sugestão do Rafael: marcar 2+ tipos ao mesmo tempo
    rows = assets_repo.list_for_grid(conn, asset_types=["hdri", "texture"])
    assert len(rows) == 7  # todos, já que a lib só tem esses dois tipos
    rows = assets_repo.list_for_grid(conn, asset_types=["hdri", "model"])
    assert _names(rows) == ["studio_small"]  # model não existe → só o hdri


def test_filtro_por_pasta_com_subpastas(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix="Texturas", include_subdirs=True)
    assert len(rows) == 5  # Concreto/2 + Madeira/1 + na_raiz_texturas + StoneQuartziteTile_2K


def test_filtro_por_pasta_sem_subpastas(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix="Texturas", include_subdirs=False)
    assert _names(rows) == ["StoneQuartziteTile_2K", "na_raiz_texturas"]


def test_raiz_sem_subpastas_mostra_so_arquivos_soltos(conn, lib):
    rows = assets_repo.list_for_grid(conn, dir_prefix=None, include_subdirs=False)
    assert _names(rows) == ["solto_na_raiz"]


def test_filtros_combinados(conn, lib):
    rows = assets_repo.list_for_grid(
        conn, search="conc", asset_types=["texture"],
        dir_prefix="Texturas/Concreto", include_subdirs=True,
    )
    assert len(rows) == 2


def test_lista_de_pastas_para_arvore(conn, lib):
    assert list_dirs(conn) == ["HDRIs", "Texturas", "Texturas/Concreto", "Texturas/Madeira"]


def test_tipos_distintos_para_o_combo(conn, lib):
    assert assets_repo.distinct_types(conn) == ["hdri", "texture"]


def test_contagem_de_extensoes_por_tipo(conn, lib):
    # 4 .jpg + 2 .png em texture; 1 .hdr em hdri (Fatia 31)
    assert assets_repo.extension_counts(conn, ["texture"]) == {"jpg": 4, "png": 2}
    assert assets_repo.extension_counts(conn, ["hdri"]) == {"hdr": 1}
    assert assets_repo.extension_counts(conn, ["model"]) == {}


def test_contagem_de_extensoes_sem_tipo_junta_tudo(conn, lib):
    assert assets_repo.extension_counts(conn) == {"hdr": 1, "jpg": 4, "png": 2}


def test_filtro_de_categoria_com_extensao(conn, lib):
    rows = assets_repo.list_for_grid(
        conn, category_filters=[{"asset_types": ["texture"], "extensions": ["jpg"]}])
    assert _names(rows) == ["Concreto Rústico 4K", "StoneQuartziteTile_2K",
                            "Wood Oak", "na_raiz_texturas"]

    rows = assets_repo.list_for_grid(
        conn, category_filters=[{"asset_types": ["texture"], "extensions": ["png"]}])
    assert _names(rows) == ["concrete_polished", "solto_na_raiz"]


def test_filtro_de_categoria_sem_extensao_traz_a_categoria_inteira(conn, lib):
    rows = assets_repo.list_for_grid(
        conn, category_filters=[{"asset_types": ["texture"], "extensions": []}])
    assert len(rows) == 6


def test_extensao_de_uma_categoria_nao_restringe_a_outra(conn, lib):
    """O bug da primeira versão da Fatia 31: `extensions` era global, então
    marcar .jpg em Imagens também exigia .jpg dos HDRIs (que só têm .hdr)."""
    rows = assets_repo.list_for_grid(conn, category_filters=[
        {"asset_types": ["texture"], "extensions": ["jpg"]},
        {"asset_types": ["hdri"], "extensions": []},
    ])
    assert _names(rows) == ["Concreto Rústico 4K", "StoneQuartziteTile_2K",
                            "Wood Oak", "na_raiz_texturas", "studio_small"]


def test_filtro_de_categoria_maiuscula_nao_diferencia(conn, lib):
    rows = assets_repo.list_for_grid(
        conn, category_filters=[{"asset_types": ["texture"], "extensions": ["JPG"]}])
    assert len(rows) == 4


def test_filtro_de_categoria_vazio_nao_restringe(conn, lib):
    assert len(assets_repo.list_for_grid(conn, category_filters=[])) == 7


def test_contagem_por_categoria_respeita_os_outros_filtros(conn, lib):
    from assetdeck.ui.categories import CATEGORIES

    contagem = assets_repo.count_by_category(conn, CATEGORIES)
    assert contagem["imagens"] == 6
    assert contagem["hdris"] == 1
    assert contagem["modelos"] == 0

    # com busca ativa, o contador prevê o resultado do clique
    contagem = assets_repo.count_by_category(conn, CATEGORIES, search="conc")
    assert contagem["imagens"] == 2
    assert contagem["hdris"] == 0


def test_contagem_por_categoria_ignora_o_proprio_filtro_de_categoria(conn, lib):
    """Senão clicar em 'Imagens' zeraria o contador de 'HDRIs' e o Rafael
    não teria como saber que ainda existe HDRI pra ver."""
    from assetdeck.ui.categories import CATEGORIES

    contagem = assets_repo.count_by_category(
        conn, CATEGORIES,
        category_filters=[{"asset_types": ["texture"], "extensions": []}])
    assert contagem["hdris"] == 1


@pytest.fixture
def lib_colorida(tmp_path, conn):
    """Biblioteca com imagens de verdade (a `lib` acima usa bytes crus, sem
    pixels) — necessário pro filtro de cor dominante (Fatia 39)."""
    from PIL import Image

    root = tmp_path / "lib_cor"
    root.mkdir()
    Image.new("RGB", (32, 32), (200, 30, 30)).save(root / "vermelho.png")
    Image.new("RGB", (32, 32), (203, 35, 33)).save(root / "vermelho_proximo.png")
    Image.new("RGB", (32, 32), (20, 60, 200)).save(root / "azul.png")
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    return root


def test_filtro_por_cor_dominante(conn, lib_colorida):
    rows = assets_repo.list_for_grid(conn, dominant_color="#c81e1e")
    assert _names(rows) == ["vermelho", "vermelho_proximo"]


def test_filtro_por_cor_dominante_sem_cor_traz_tudo(conn, lib_colorida):
    assert len(assets_repo.list_for_grid(conn, dominant_color=None)) == 3


# ------------------------------------------ cor perceptual (Fatia 76) --

def test_verde_da_paleta_acha_folhagem_dessaturada():
    """Regressão do bug que o Rafael relatou: "clico para filtrar por cor
    verde e as texturas de folha nem aparecem".

    Folha fotográfica é verde-oliva DESSATURADO. Com distância euclidiana em
    RGB ela ficava a ~94 do verde da paleta, contra uma tolerância de 90 —
    passava raspando, e "Verde" devolvia ZERO numa biblioteca cheia de
    folhagem. Estes hex saíram de arquivos reais da testlib.
    """
    from assetdeck.db.connection import _color_distance
    from assetdeck.db.repos.assets import COLOR_TOLERANCE
    from assetdeck.ui.main_window import PALETA_CORES

    verde = dict((rot, val) for rot, val in PALETA_CORES)["Verde"]
    for folha in ("#4f6338", "#7e8d70", "#79876a", "#4a5d37"):
        d = _color_distance(folha, verde)
        assert d <= COLOR_TOLERANCE, f"{folha} ficou fora do verde ({d:.1f})"


def test_a_cor_nao_vaza_entre_familias_distantes():
    """A tolerância não pode ser afrouxada até tudo casar com tudo — é o
    outro jeito de o filtro virar inútil."""
    from assetdeck.db.connection import _color_distance
    from assetdeck.db.repos.assets import COLOR_TOLERANCE

    verde = "#43a047"
    for estranho in ("#f1c40f", "#2980b9", "#7f5539", "#8e44ad"):
        d = _color_distance(estranho, verde)
        assert d > COLOR_TOLERANCE, f"{estranho} não devia casar com verde ({d:.1f})"


def test_cinza_e_cor_nunca_se_misturam():
    """Acromático (cinza/branco/preto) e colorido são famílias diferentes:
    filtrar "Cinza" não pode trazer folhagem, nem "Verde" trazer concreto."""
    from assetdeck.db.connection import _color_distance
    from assetdeck.db.repos.assets import COLOR_TOLERANCE

    assert _color_distance("#a4a4a4", "#43a047") > COLOR_TOLERANCE
    assert _color_distance("#4f6338", "#7f8c8d") > COLOR_TOLERANCE
    # …mas os acromáticos ainda se distinguem ENTRE si por claro/escuro.
    assert _color_distance("#f5f5f5", "#1a1a1a") > COLOR_TOLERANCE
    assert _color_distance("#eeeeee", "#f5f5f5") <= COLOR_TOLERANCE
