"""Detecção de dependências: texturas que acompanham um .blend/.fbx irmão."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.dependencies import attach_pack_previews, detect
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
