"""Previews customizados: cópia gerenciada, capa, galeria e soft delete."""

import pytest
from PIL import Image

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "modelo.blend").write_bytes(b"blend" * 40)
    Image.new("RGB", (64, 64)).save(root / "textura.jpg")
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    # A "imagem do usuário" vem de FORA da biblioteca:
    externa = tmp_path / "meu_render.png"
    Image.new("RGB", (128, 128), (200, 40, 40)).save(externa)
    yield conn, root, tmp_path / "previews", externa
    conn.close()


def _id(conn, name):
    return conn.execute("SELECT id FROM assets WHERE name = ?", (name,)).fetchone()["id"]


def test_add_copia_para_pasta_gerenciada_e_vira_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")

    stored = previews_repo.add(conn, aid, externa, pdir)

    assert stored.parent == pdir          # cópia na pasta do APP…
    assert stored.exists()
    assert externa.exists()               # …e o original do usuário intacto
    galeria = previews_repo.list_for(conn, aid)
    assert len(galeria) == 1
    assert galeria[0]["is_cover"] == 1
    assert galeria[0]["origin"] == "user"


def test_novo_preview_assume_a_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    previews_repo.add(conn, aid, externa, pdir)
    previews_repo.add(conn, aid, externa, pdir)  # segundo

    galeria = previews_repo.list_for(conn, aid)
    assert len(galeria) == 2
    assert [p["is_cover"] for p in galeria] == [0, 1]  # o novo é a capa


def test_set_cover_troca_a_capa(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    previews_repo.add(conn, aid, externa, pdir)
    previews_repo.add(conn, aid, externa, pdir)
    primeiro = previews_repo.list_for(conn, aid)[0]

    previews_repo.set_cover(conn, primeiro["id"])

    galeria = previews_repo.list_for(conn, aid)
    assert [p["is_cover"] for p in galeria] == [1, 0]


def test_grid_ve_cover_path_so_na_visao_agrupada(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    stored = previews_repo.add(conn, aid, externa, pdir)

    agrupado = {r["name"]: r for r in assets_repo.list_for_grid(conn)}
    assert agrupado["modelo"]["cover_path"] == str(stored)
    assert agrupado["textura"]["cover_path"] is None

    expandido = {r["name"]: r for r in assets_repo.list_for_grid(conn, expand_sets=True)}
    assert expandido["modelo"]["cover_path"] is None  # modo expandido: sem capa


def test_soft_delete_tira_da_galeria_mas_preserva_o_arquivo(env):
    conn, _, pdir, externa = env
    aid = _id(conn, "modelo")
    stored = previews_repo.add(conn, aid, externa, pdir)
    pid = previews_repo.list_for(conn, aid)[0]["id"]

    previews_repo.soft_delete(conn, pid)

    assert previews_repo.list_for(conn, aid) == []
    assert stored.exists()  # nada apagado de verdade
    modelo = next(r for r in assets_repo.list_for_grid(conn) if r["name"] == "modelo")
    assert modelo["cover_path"] is None  # a grid volta à thumb normal


def test_ocultar_asset_some_da_grid_e_reexibir_volta(env):
    """Fatia 10b: imagem que virou preview de model pode ser ocultada."""
    conn, _, _, _ = env
    aid = _id(conn, "textura")

    assets_repo.set_hidden(conn, aid, True)
    nomes = {r["name"] for r in assets_repo.list_for_grid(conn)}
    assert "textura" not in nomes                     # sumiu da visão padrão

    com_ocultos = {r["name"] for r in assets_repo.list_for_grid(conn, include_hidden=True)}
    assert "textura" in com_ocultos                   # 'Mostrar ocultos' acha

    assets_repo.set_hidden(conn, aid, False)
    nomes = {r["name"] for r in assets_repo.list_for_grid(conn)}
    assert "textura" in nomes                         # reexibido


def test_preview_interno_a_partir_de_outro_asset(env):
    """O fluxo da 10b em nível de repositório: imagem da biblioteca vira
    preview do model, e a origem continua existindo (oculta ou não)."""
    conn, root, pdir, _ = env
    modelo = _id(conn, "modelo")
    origem = assets_repo.primary_abs_path(conn, _id(conn, "textura"), root)

    stored = previews_repo.add(conn, modelo, origem, pdir)

    assert stored.exists()
    linha = next(r for r in assets_repo.list_for_grid(conn) if r["name"] == "modelo")
    assert linha["cover_path"] == str(stored)
    assert origem.exists()  # arquivo da biblioteca intocado


def test_config_lembra_escolha_de_ocultar(tmp_path, monkeypatch):
    from assetdeck import config

    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    cfg = config.load_config()
    assert cfg["hide_preview_source"] == "ask"

    cfg["hide_preview_source"] = "always"
    config.save_config(cfg)

    assert config.load_config()["hide_preview_source"] == "always"


def test_add_de_arquivo_inexistente_da_erro_legivel(env):
    conn, _, pdir, _ = env
    with pytest.raises(FileNotFoundError):
        previews_repo.add(conn, _id(conn, "modelo"), pdir / "nada.png", pdir)
