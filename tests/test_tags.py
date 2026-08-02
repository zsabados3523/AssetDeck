"""Tags: hierarquia, aliases PT/EN, filtro, FTS e sobrevivência via sidecar."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.sidecar.writer import write_for_asset


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "oak_planks.jpg").write_bytes(b"a" * 50)
    (root / "pine_bark.jpg").write_bytes(b"b" * 50)
    (root / "steel_plate.jpg").write_bytes(b"c" * 50)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root, tmp_path
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_hierarquia_e_caminho(env):
    conn, _, _ = env
    materiais = tags_repo.create(conn, "Materiais")
    madeira = tags_repo.create(conn, "Wood", parent_id=materiais)
    nogueira = tags_repo.create(conn, "Oak", parent_id=madeira)

    assert tags_repo.tag_path(conn, nogueira) == "Materiais/Wood/Oak"
    assert set(tags_repo.descendants(conn, materiais)) == {materiais, madeira, nogueira}


def test_criar_tag_duplicada_devolve_a_existente(env):
    conn, _, _ = env
    a = tags_repo.create(conn, "Wood")
    b = tags_repo.create(conn, "Wood")
    assert a == b


def test_filtro_por_tag_inclui_subtags(env):
    conn, _, _ = env
    madeira = tags_repo.create(conn, "Wood")
    oak = tags_repo.create(conn, "Oak", parent_id=madeira)
    tags_repo.assign(conn, _id(conn, "oak_planks"), oak)
    tags_repo.assign(conn, _id(conn, "pine_bark"), madeira)

    rows = assets_repo.list_for_grid(conn, tag_id=madeira)  # tag PAI

    assert {r["name"] for r in rows} == {"oak_planks", "pine_bark"}


def test_busca_madeira_acha_pack_wood_via_alias(env):
    """O critério da fatia, direto do brief."""
    conn, _, _ = env
    wood = tags_repo.create(conn, "Wood")
    tags_repo.add_alias(conn, wood, "madeira", lang="pt")
    tags_repo.assign(conn, _id(conn, "oak_planks"), wood)
    assets_repo.rebuild_fts(conn)

    rows = assets_repo.list_for_grid(conn, search="madeira")

    assert [r["name"] for r in rows] == ["oak_planks"]


def test_busca_pelo_nome_da_tag_pai_acha_asset_na_subtag(env):
    conn, _, _ = env
    wood = tags_repo.create(conn, "Wood")
    oak = tags_repo.create(conn, "Oak", parent_id=wood)
    tags_repo.assign(conn, _id(conn, "oak_planks"), oak)
    assets_repo.rebuild_fts(conn)

    rows = assets_repo.list_for_grid(conn, search="wood")
    assert [r["name"] for r in rows] == ["oak_planks"]


def test_substituir_tags_via_set_tags(env):
    conn, _, _ = env
    a = tags_repo.create(conn, "A")
    b = tags_repo.create(conn, "B")
    c = tags_repo.create(conn, "C")
    alvo = _id(conn, "steel_plate")
    tags_repo.set_tags(conn, alvo, [a, b])
    tags_repo.set_tags(conn, alvo, [c], replace=True)  # 'substituir'

    assert [t["name"] for t in tags_repo.tags_of(conn, alvo)] == ["C"]


def test_soft_delete_de_tag_some_da_lista_e_do_filtro(env):
    conn, _, _ = env
    wood = tags_repo.create(conn, "Wood")
    oak = tags_repo.create(conn, "Oak", parent_id=wood)
    tags_repo.assign(conn, _id(conn, "oak_planks"), oak)

    tags_repo.soft_delete(conn, wood)  # leva a subtag junto

    assert tags_repo.list_tree(conn) == []
    assert tags_repo.tags_of(conn, _id(conn, "oak_planks")) == []


def test_recriar_tag_apos_soft_delete_reaproveita_e_reativa(env):
    """Bug: apagar 'Materiais' e criar 'Materiais' de novo não podia sumir da UI."""
    conn, _, _ = env
    materiais = tags_repo.create(conn, "Materiais")
    tags_repo.soft_delete(conn, materiais)
    assert tags_repo.list_tree(conn) == []

    materiais_novo = tags_repo.create(conn, "Materiais")

    assert materiais_novo == materiais  # reaproveita a linha, não tenta inserir outra
    assert [t["name"] for t in tags_repo.list_tree(conn)] == ["Materiais"]


def test_recriar_subtag_apos_soft_delete_reaproveita_e_reativa(env):
    conn, _, _ = env
    materiais = tags_repo.create(conn, "Materiais")
    concreto = tags_repo.create(conn, "Concreto", parent_id=materiais)
    tags_repo.soft_delete(conn, concreto)

    concreto_novo = tags_repo.create(conn, "Concreto", parent_id=materiais)

    assert concreto_novo == concreto
    nomes = {t["name"] for t in tags_repo.list_tree(conn)}
    assert nomes == {"Materiais", "Concreto"}


def test_icone_da_tag_persiste_e_volta_na_arvore(env):
    """A coluna tags.icon existe desde o v1 mas só ganhou uso na Fatia 33."""
    conn, _, _ = env
    madeira = tags_repo.create(conn, "Madeira")
    tags_repo.set_icon(conn, madeira, "tag-madeira")

    linha = next(r for r in tags_repo.list_tree(conn) if r["id"] == madeira)
    assert linha["icon"] == "tag-madeira"


def test_icone_chega_junto_com_as_tags_do_asset(env):
    """O painel de detalhes desenha a partir de tags_of."""
    conn, _, _ = env
    madeira = tags_repo.create(conn, "Madeira")
    tags_repo.set_icon(conn, madeira, "tag-madeira")
    tags_repo.assign(conn, _id(conn, "oak_planks"), madeira)

    linha = tags_repo.tags_of(conn, _id(conn, "oak_planks"))[0]
    assert linha["icon"] == "tag-madeira"


def test_set_icon_com_none_limpa(env):
    conn, _, _ = env
    t = tags_repo.create(conn, "Metal", icon="tag-metal")
    tags_repo.set_icon(conn, t, None)

    linha = next(r for r in tags_repo.list_tree(conn) if r["id"] == t)
    assert linha["icon"] is None


def test_icone_sobrevive_ao_renomear(env):
    conn, _, _ = env
    t = tags_repo.create(conn, "Metal", icon="tag-metal")
    tags_repo.rename(conn, t, "Metais")

    linha = next(r for r in tags_repo.list_tree(conn) if r["id"] == t)
    assert linha["name"] == "Metais"
    assert linha["icon"] == "tag-metal"


def test_tags_sobrevivem_ao_desastre_via_sidecar(env):
    """Banco morre → sidecar devolve tags com hierarquia completa."""
    conn, root, tmp_path = env
    materiais = tags_repo.create(conn, "Materiais")
    wood = tags_repo.create(conn, "Wood", parent_id=materiais)
    alvo = _id(conn, "oak_planks")
    tags_repo.assign(conn, alvo, wood)
    write_for_asset(conn, root, alvo)
    conn.close()

    conn2 = connect(tmp_path / "renascido.db")
    apply_migrations(conn2)
    lib_id = libraries_repo.get_or_create(conn2, root)
    scan_library(conn2, lib_id, root)

    novo_id = conn2.execute(
        "SELECT id FROM assets WHERE name = 'oak_planks'"
    ).fetchone()["id"]
    caminhos = [tags_repo.tag_path(conn2, t["id"])
                for t in tags_repo.tags_of(conn2, novo_id)]
    assert caminhos == ["Materiais/Wood"]  # árvore recriada + tag religada
    conn2.close()
