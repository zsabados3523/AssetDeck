"""Detecção de dependências: texturas que acompanham um .blend/.fbx irmão."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.dependencies import (
    attach_pack_previews,
    attach_stem_match_previews,
    detect,
)
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    """Reproduz a estrutura REAL da biblioteca do Rafael."""
    root = tmp_path / "lib"

    # 1) Material convertido em .blend, com os mapas numa subpasta 4K
    mat = root / "MATERIAIS" / "Poliigon_Quartzite"
    (mat / "4K").mkdir(parents=True)
    (mat / "Poliigon_Quartzite.blend").write_bytes(b"blend" * 20)
    (mat / "Poliigon_Quartzite_Preview1.png").write_bytes(b"prev" * 20)
    (mat / "4K" / "Quartzite_BaseColor.jpg").write_bytes(b"c" * 40)
    (mat / "4K" / "Quartzite_Normal.jpg").write_bytes(b"n" * 40)

    # 2) Modelo com texturas em subpasta
    mod = root / "MODELOS" / "Arvore"
    (mod / "textures").mkdir(parents=True)
    (mod / "Arvore.blend").write_bytes(b"blend" * 20)
    (mod / "textures" / "Leaf_BaseColor.png").write_bytes(b"l" * 40)

    # 3) Textura AVULSA (sem modelo por perto) — NÃO é dependência
    (root / "TEXTURAS").mkdir(parents=True)
    (root / "TEXTURAS" / "Concreto_Color.jpg").write_bytes(b"x" * 40)

    # 4) HDRI avulso — nunca é dependência
    (root / "HDRIs").mkdir()
    (root / "HDRIs" / "ceu.hdr").write_bytes(b"h" * 40)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root, tmp_path
    conn.close()


def _por_nome(conn, **kw):
    return {r["name"]: r for r in assets_repo.list_for_grid(conn, **kw)}


def test_mapas_de_material_com_blend_viram_dependencia(env):
    conn, lib_id, _, _ = env
    detect(conn, lib_id)

    deps = {r["name"] for r in assets_repo.list_for_grid(conn)
            if r["is_dependency"]}
    assert "Quartzite_BaseColor" in deps
    assert "Quartzite_Normal" in deps


def test_texturas_de_modelo_viram_dependencia(env):
    conn, lib_id, _, _ = env
    detect(conn, lib_id)
    linha = _por_nome(conn)["Leaf_BaseColor"]
    assert linha["is_dependency"] == 1


def test_texturas_de_outros_programas_tambem_viram_dependencia(tmp_path):
    """Fatia 37: .rvt/.skp/.usdz/.abc entram como asset_type='model' (só
    reconhecer e catalogar) — prova que o mecanismo de dependência, que
    olha só asset_type e não a extensão, funciona pra eles sem mudança
    nenhuma em dependencies.py."""
    root = tmp_path / "lib"
    for nome_pasta, nome_arquivo in [
        ("Projeto_Revit", "Projeto.rvt"),
        ("Fachada_SketchUp", "fachada.skp"),
        ("Cena_USD", "cena.usdz"),
        ("Anim_Alembic", "anim.abc"),
    ]:
        pasta = root / "MODELOS" / nome_pasta
        (pasta / "textures").mkdir(parents=True)
        (pasta / nome_arquivo).write_bytes(b"x" * 30)
        (pasta / "textures" / "mapa_Color.jpg").write_bytes(b"c" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    detect(conn, lib_id)

    todas = assets_repo.list_for_grid(conn)
    # o nome "mapa_Color" se repete nas 4 pastas — não pode virar dict por
    # nome, senão 3 das 4 linhas somem silenciosamente da checagem
    por_caminho = {r["rel_path"]: r for r in todas}

    for nome_pasta, nome_arquivo in [
        ("Projeto_Revit", "Projeto.rvt"), ("Fachada_SketchUp", "fachada.skp"),
        ("Cena_USD", "cena.usdz"), ("Anim_Alembic", "anim.abc"),
    ]:
        modelo = por_caminho[f"MODELOS/{nome_pasta}/{nome_arquivo}"]
        assert modelo["asset_type"] == "model"
        assert modelo["is_dependency"] == 0

        mapa = por_caminho[f"MODELOS/{nome_pasta}/textures/mapa_Color.jpg"]
        assert mapa["is_dependency"] == 1


def test_pack_com_blend_e_mapas_em_pastas_irmas(tmp_path):
    """Caso REAL (Maxtree): .blend e mapas em subpastas irmãs do mesmo pack."""
    root = tmp_path / "lib"
    pack = root / "MODELOS" / "Maxtree Vol 148"
    (pack / "Blender_CyclesEevee").mkdir(parents=True)
    (pack / "Maps").mkdir(parents=True)
    (pack / "Blender_CyclesEevee" / "palmeira_01.blend").write_bytes(b"b" * 30)
    (pack / "Maps" / "Leaf_01_albedo.jpg").write_bytes(b"a" * 30)
    (root / "TEXTURAS").mkdir(parents=True)
    (root / "TEXTURAS" / "avulsa_Color.jpg").write_bytes(b"x" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    detect(conn, lib_id)

    linhas = {r["name"]: r for r in assets_repo.list_for_grid(conn)}
    assert linhas["Leaf_01_albedo"]["is_dependency"] == 1  # mapa do pack
    assert linhas["palmeira_01"]["is_dependency"] == 0     # o modelo, não
    assert linhas["avulsa_Color"]["is_dependency"] == 0    # fora do pack
    conn.close()


def test_textura_avulsa_nao_e_dependencia(env):
    conn, lib_id, _, _ = env
    detect(conn, lib_id)
    assert _por_nome(conn)["Concreto_Color"]["is_dependency"] == 0


def test_modelos_e_hdris_nunca_sao_dependencia(env):
    conn, lib_id, _, _ = env
    detect(conn, lib_id)
    linhas = _por_nome(conn)
    assert linhas["Poliigon_Quartzite"]["is_dependency"] == 0
    assert linhas["Arvore"]["is_dependency"] == 0
    assert linhas["ceu"]["is_dependency"] == 0


def test_filtro_esconde_dependencias(env):
    """O que o Rafael pediu: desligar as texturas e ver só o .blend."""
    conn, lib_id, _, _ = env
    detect(conn, lib_id)

    com = _por_nome(conn, include_dependencies=True)
    sem = _por_nome(conn, include_dependencies=False)

    assert "Quartzite_BaseColor" in com
    assert "Quartzite_BaseColor" not in sem
    assert "Poliigon_Quartzite" in sem   # o .blend do material fica
    assert "Concreto_Color" in sem       # textura avulsa fica
    assert len(sem) < len(com)


def test_detect_e_idempotente(env):
    conn, lib_id, _, _ = env
    assert detect(conn, lib_id) > 0   # primeira passada marca
    assert detect(conn, lib_id) == 0  # segunda não muda nada


def test_dependencia_deixa_de_ser_se_o_modelo_sumir(env):
    conn, lib_id, root, _ = env
    detect(conn, lib_id)
    assert _por_nome(conn)["Leaf_BaseColor"]["is_dependency"] == 1

    (root / "MODELOS" / "Arvore" / "Arvore.blend").unlink()
    scan_library(conn, lib_id, root)  # marca o .blend como sumido
    conn.execute("UPDATE assets SET deleted_at = datetime('now') "
                 "WHERE name = 'Arvore'")
    conn.commit()
    detect(conn, lib_id)

    assert _por_nome(conn)["Leaf_BaseColor"]["is_dependency"] == 0


def test_preview_do_pack_vira_capa_do_blend(env):
    """Poliigon entrega *_Preview1.png — melhor que renderizar."""
    conn, lib_id, root, tmp_path = env
    alvo = conn.execute(
        "SELECT id FROM assets WHERE name = 'Poliigon_Quartzite'"
    ).fetchone()["id"]

    criadas = attach_pack_previews(conn, lib_id, root, tmp_path / "previews")

    assert criadas >= 1
    galeria = previews_repo.list_for(conn, alvo)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "auto"


def test_preview_do_pack_nao_duplica_em_revarredura(env):
    conn, lib_id, root, tmp_path = env
    attach_pack_previews(conn, lib_id, root, tmp_path / "previews")
    criadas2 = attach_pack_previews(conn, lib_id, root, tmp_path / "previews")
    assert criadas2 == 0  # já tem capa: não mexe


# ---- preview automático por nome igual (Fatia 57) ----

@pytest.fixture
def env_nomes(tmp_path):
    """'Cadeira.blend' + 'Cadeira.jpg' na mesma pasta — o caso que o
    Rafael pediu — e os cantos que não podem virar match errado."""
    root = tmp_path / "lib"
    pasta = root / "MOVEIS"
    pasta.mkdir(parents=True)

    # 1) Casamento simples: mesmo nome-base, mesma pasta
    (pasta / "Cadeira.blend").write_bytes(b"b" * 30)
    (pasta / "Cadeira.jpg").write_bytes(b"j" * 30)

    # 2) Ambíguo: DUAS imagens com o mesmo nome-base do modelo
    (pasta / "Mesa.blend").write_bytes(b"b" * 30)
    (pasta / "Mesa.jpg").write_bytes(b"j" * 30)
    (pasta / "Mesa.png").write_bytes(b"p" * 30)

    # 3) Sem imagem nenhuma de mesmo nome
    (pasta / "Sofa.blend").write_bytes(b"b" * 30)

    # 4) Nome bate, mas a imagem está em OUTRA pasta — não pode casar
    (pasta / "Banco.blend").write_bytes(b"b" * 30)
    outra = root / "OUTRAPASTA"
    outra.mkdir(parents=True)
    (outra / "Banco.jpg").write_bytes(b"j" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root, tmp_path
    conn.close()


def _id_por_caminho(conn, rel_path):
    """`assets.name` é só o stem (`path.stem`) — '.blend' e '.jpg' do
    mesmo nome-base viram DOIS assets com o mesmo `name`, então não dá
    pra achar por nome sem ambiguidade. `rel_path` é único."""
    return conn.execute(
        "SELECT a.id FROM assets a JOIN files f ON f.asset_id = a.id "
        "WHERE f.rel_path = ? AND f.is_primary = 1", (rel_path,),
    ).fetchone()["id"]


def test_casa_modelo_com_imagem_de_mesmo_nome(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    cadeira_id = _id_por_caminho(conn, "MOVEIS/Cadeira.blend")

    criadas = attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert criadas == 1
    galeria = previews_repo.list_for(conn, cadeira_id)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "auto"


def test_ambiguo_e_pulado_sem_criar_nada(env_nomes):
    """2+ imagens com o mesmo nome-base do modelo: não adivinha qual usar
    (regra do projeto — nenhum erro/ambiguidade mascarada)."""
    conn, lib_id, root, tmp_path = env_nomes
    mesa_id = _id_por_caminho(conn, "MOVEIS/Mesa.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert previews_repo.list_for(conn, mesa_id) == []


def test_sem_imagem_de_mesmo_nome_nao_cria_nada(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    sofa_id = _id_por_caminho(conn, "MOVEIS/Sofa.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert previews_repo.list_for(conn, sofa_id) == []


def test_pasta_diferente_nao_casa_por_engano(env_nomes):
    """'OUTRAPASTA/Banco.jpg' tem o MESMO nome-base de 'MOVEIS/Banco.blend',
    mas as duas pastas estão na RAIZ da biblioteca.

    Desde a Fatia 81 o casamento aceita pasta irmã (mesmo pacote), mas raiz
    não é pacote — é a biblioteca inteira. Este teste, escrito na Fatia 57,
    foi justamente quem pegou o exagero da primeira versão daquela mudança:
    com a regra afrouxada sem ressalva, estes dois passavam a casar."""
    conn, lib_id, root, tmp_path = env_nomes
    banco_id = _id_por_caminho(conn, "MOVEIS/Banco.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert previews_repo.list_for(conn, banco_id) == []


def test_nao_mexe_em_modelo_que_ja_tem_capa(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    cadeira_id = _id_por_caminho(conn, "MOVEIS/Cadeira.blend")
    outra_imagem = tmp_path / "capa_manual.jpg"
    outra_imagem.write_bytes(b"m" * 30)
    previews_repo.add(conn, cadeira_id, outra_imagem, tmp_path / "previews", origin="user")

    criadas = attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert criadas == 0
    galeria = previews_repo.list_for(conn, cadeira_id)
    assert len(galeria) == 1
    assert galeria[0]["origin"] == "user"  # a manual continua sendo a capa


def test_nao_duplica_em_revarredura(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")
    criadas2 = attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")
    assert criadas2 == 0  # já tem capa: não mexe


def test_hide_source_desligado_por_padrao_nao_oculta(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    imagem_id = _id_por_caminho(conn, "MOVEIS/Cadeira.jpg")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    linha = assets_repo.list_for_grid(conn, include_hidden=True)
    hidden = next(r for r in linha if r["id"] == imagem_id)["hidden"]
    assert hidden == 0


def test_hide_source_ligado_oculta_a_imagem_usada(env_nomes):
    conn, lib_id, root, tmp_path = env_nomes
    imagem_id = _id_por_caminho(conn, "MOVEIS/Cadeira.jpg")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews", hide_source=True)

    linha = assets_repo.list_for_grid(conn, include_hidden=True)
    hidden = next(r for r in linha if r["id"] == imagem_id)["hidden"]
    assert hidden == 1


# ------------------------------------------ pasta irmã (Fatia 81) --

@pytest.fixture
def env_pack(tmp_path):
    """Um pack comercial de verdade: modelos e prévias em pastas IRMÃS.

    É como o Maxtree se organiza, e era o caso que a regra de "mesma pasta"
    não alcançava — o Rafael relatou a função como se estivesse quebrada.
    """
    root = tmp_path / "lib"
    pack = root / "VEGETACAO" / "Maxtree Vol 148"
    modelos = pack / "Blender_CyclesEevee"
    thumbs = pack / "Thumbnails"
    modelos.mkdir(parents=True)
    thumbs.mkdir(parents=True)

    (modelos / "MT_Palmeira_01.blend").write_bytes(b"b" * 30)
    (thumbs / "MT_Palmeira_01.jpg").write_bytes(b"j" * 30)

    # Dois modelos disputando a mesma prévia: ambíguo do lado do MODELO.
    # É o caso REAL do Maxtree, que entrega o mesmo modelo numa pasta por
    # renderizador — as duas são irmãs, no mesmo pacote.
    octane = pack / "Blender_Octane"
    octane.mkdir(parents=True)
    (modelos / "MT_Repetido.blend").write_bytes(b"b" * 30)
    (octane / "MT_Repetido.blend").write_bytes(b"b" * 30)
    (thumbs / "MT_Repetido.jpg").write_bytes(b"j" * 30)

    # pack VIZINHO com nome igual: não pode atravessar a fronteira do pacote
    outro = root / "VEGETACAO" / "Maxtree Vol 149"
    (outro / "Thumbnails").mkdir(parents=True)
    (outro / "Thumbnails" / "MT_Sozinho.jpg").write_bytes(b"j" * 30)
    (pack / "Blender_CyclesEevee" / "MT_Sozinho.blend").write_bytes(b"b" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root, tmp_path
    conn.close()


def test_casa_com_imagem_em_pasta_irma_do_mesmo_pacote(env_pack):
    """O caso que motivou a fatia: modelo em 'Blender_CyclesEevee/' e
    prévia em 'Thumbnails/', irmãs dentro do mesmo pack."""
    conn, lib_id, root, tmp_path = env_pack
    modelo_id = _id_por_caminho(
        conn, "VEGETACAO/Maxtree Vol 148/Blender_CyclesEevee/MT_Palmeira_01.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    galeria = previews_repo.list_for(conn, modelo_id)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "auto"


def test_dois_modelos_de_mesmo_nome_no_pacote_e_ambiguo(env_pack):
    """Ambiguidade do lado do MODELO — antes da Fatia 81 nem era detectada:
    o dicionário guardava um par só e o segundo modelo sobrescrevia o
    primeiro em silêncio, dando a capa pra um deles ao acaso."""
    conn, lib_id, root, tmp_path = env_pack
    a = _id_por_caminho(
        conn, "VEGETACAO/Maxtree Vol 148/Blender_CyclesEevee/MT_Repetido.blend")
    b = _id_por_caminho(
        conn, "VEGETACAO/Maxtree Vol 148/Blender_Octane/MT_Repetido.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert previews_repo.list_for(conn, a) == []
    assert previews_repo.list_for(conn, b) == []


def test_nao_atravessa_a_fronteira_do_pacote(env_pack):
    """'Vol 149/Thumbnails/MT_Sozinho.jpg' tem o nome do modelo que está no
    'Vol 148' — packs diferentes não se misturam."""
    conn, lib_id, root, tmp_path = env_pack
    modelo_id = _id_por_caminho(
        conn, "VEGETACAO/Maxtree Vol 148/Blender_CyclesEevee/MT_Sozinho.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert previews_repo.list_for(conn, modelo_id) == []


# --------------------------------------- Chaos Cosmos (Fatia 84) --

@pytest.fixture
def env_cosmos(tmp_path):
    """A estrutura REAL do Chaos Cosmos, copiada da biblioteca do Rafael:

        Furniture/Chair_125_029/Chair_125_029.blend
        Furniture/Chair_125_029/previews/Chair_125_029_01.png
        Furniture/Chair_125_029/previews/Chair_125_029_02.png

    Vários previews por modelo, com sufixo de sequência, numa SUBPASTA.
    """
    root = tmp_path / "lib"

    # caso comum: prévias com o nome do modelo + _01/_02
    a = root / "Furniture" / "Chair_125_029"
    (a / "previews").mkdir(parents=True)
    (a / "Chair_125_029.blend").write_bytes(b"b" * 30)
    (a / "previews" / "Chair_125_029_01.png").write_bytes(b"j" * 30)
    (a / "previews" / "Chair_125_029_02.png").write_bytes(b"j" * 30)

    # ~11% do Cosmos: prévias com nome de hash, sem relação com o modelo
    b = root / "Furniture" / "Kitchen_Props_187_029"
    (b / "previews").mkdir(parents=True)
    (b / "Kitchen_Props_187_029.blend").write_bytes(b"b" * 30)
    (b / "previews" / "a586041c_1755512249817171783.png").write_bytes(b"j" * 30)
    (b / "previews" / "e76a21c7_1755512249334076233.png").write_bytes(b"j" * 30)

    # o modelo já termina em número de catálogo: não pode virar "Coffee_Table"
    c = root / "Furniture" / "Coffee_Table_273_006_001"
    (c / "previews").mkdir(parents=True)
    (c / "Coffee_Table_273_006_001.blend").write_bytes(b"b" * 30)
    (c / "previews" / "Coffee_Table_273_006_001_01.png").write_bytes(b"j" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root, tmp_path
    conn.close()


def test_cosmos_usa_o_primeiro_preview_como_capa(env_cosmos):
    """Vários previews numerados não são ambiguidade — são uma SEQUÊNCIA de
    ângulos. O `_01` é a capa natural."""
    conn, lib_id, root, tmp_path = env_cosmos
    modelo = _id_por_caminho(conn, "Furniture/Chair_125_029/Chair_125_029.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    galeria = previews_repo.list_for(conn, modelo)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "auto"


def test_cosmos_casa_preview_de_nome_hash_pela_pasta(env_cosmos):
    """Prévia chamada 'a586041c_1755512249817171783.png' não tem relação
    NENHUMA com o nome do modelo — só a pasta 'previews/' as liga."""
    conn, lib_id, root, tmp_path = env_cosmos
    modelo = _id_por_caminho(
        conn, "Furniture/Kitchen_Props_187_029/Kitchen_Props_187_029.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    assert len(previews_repo.list_for(conn, modelo)) == 1


def test_numero_de_catalogo_do_modelo_nao_e_confundido_com_sequencia(env_cosmos):
    """'Coffee_Table_273_006_001.blend' termina em número, mas isso é o
    CATÁLOGO, não um sufixo de sequência. Normalizar o nome do modelo o
    reduziria a 'Coffee_Table' e ele casaria com qualquer mesa de centro —
    por isso só o nome da IMAGEM é normalizado."""
    conn, lib_id, root, tmp_path = env_cosmos
    modelo = _id_por_caminho(
        conn,
        "Furniture/Coffee_Table_273_006_001/Coffee_Table_273_006_001.blend")

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    galeria = previews_repo.list_for(conn, modelo)
    assert len(galeria) == 1, "o modelo com número de catálogo ficou sem capa"


def test_pasta_previews_com_dois_modelos_nao_adivinha(tmp_path):
    """A regra de PASTA só vale onde há um modelo — com dois, não dá pra
    saber de quem é a prévia de nome de hash."""
    root = tmp_path / "lib"
    pasta = root / "Furniture" / "Combo"
    (pasta / "previews").mkdir(parents=True)
    (pasta / "Sofa.blend").write_bytes(b"b" * 30)
    (pasta / "Mesa.blend").write_bytes(b"b" * 30)
    (pasta / "previews" / "hash_123456.png").write_bytes(b"j" * 30)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    attach_stem_match_previews(conn, lib_id, root, tmp_path / "previews")

    for nome in ("Sofa", "Mesa"):
        aid = _id_por_caminho(conn, f"Furniture/Combo/{nome}.blend")
        assert previews_repo.list_for(conn, aid) == []
    conn.close()
