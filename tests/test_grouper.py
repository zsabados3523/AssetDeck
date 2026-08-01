"""Agrupador PBR: parsing de nomes reais, fusão, travas e idempotência."""

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.grouper import apply_grouping, parse_stem
from assetdeck.indexer.scanner import scan_library


# ---- parsing (padrões copiados de arquivos REAIS da testlib) ----

@pytest.mark.parametrize("stem,base,role", [
    ("Poliigon_MetalSteelCorrugated_9023_Displacement",
     "poliigon metalsteelcorrugated 9023", "height"),
    ("MetalWireMesh001_ROUGHNESS_1K_METALNESS", "metalwiremesh001", "roughness"),
    ("MetalDesignerWeaveSteel001_DISP16_4K_METALNESS",
     "metaldesignerweavesteel001", "height"),
    ("Green_leaf_10_2K_front_Base_Color", "green leaf 10 front", "basecolor"),
    ("Bricks074_2K-JPG_NormalGL", "bricks074", "normal"),
    ("Wood051_2K_Color", "wood051", "basecolor"),
    ("TreeBark1_normal", "treebark1", "normal"),
    ("concrete_ao", "concrete", "ao"),
])
def test_parse_stem_padroes_reais(stem, base, role):
    assert parse_stem(stem) == (base, role)


def test_parse_stem_sem_papel_retorna_none():
    assert parse_stem("foto_das_ferias_2024") == ("foto das ferias 2024", None)
    assert parse_stem("belfast_farmhouse_4k") == ("belfast farmhouse 4k", None)


# ---- integração ----

@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    (root / "Bricks").mkdir(parents=True)
    # Um set PBR clássico de 4 mapas:
    for mapa in ("Color", "NormalGL", "Roughness", "Displacement"):
        (root / "Bricks" / f"Bricks074_2K_{mapa}.jpg").write_bytes(
            mapa.encode() * 30
        )
    # Coisas que NÃO podem ser agrupadas:
    (root / "foto_avulsa.jpg").write_bytes(b"f" * 40)
    (root / "gemeo_a.jpg").write_bytes(b"a" * 40)   # sem papel no nome
    (root / "gemeo_b.jpg").write_bytes(b"b" * 40)
    # Par sem papel-âncora (só metal+spec) — guarda anti-falso-positivo:
    (root / "duvida_Metal.jpg").write_bytes(b"m" * 40)
    (root / "duvida_Spec.jpg").write_bytes(b"s" * 40)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root
    conn.close()


def test_set_pbr_vira_um_asset_com_capa_no_basecolor(env):
    conn, lib_id, _ = env
    antes = assets_repo.count_active(conn)  # 9 assets 1:1

    stats = apply_grouping(conn, lib_id)

    assert stats.sets_created == 1
    assert stats.files_grouped == 4
    assert assets_repo.count_active(conn) == antes - 3  # 4 viraram 1

    set_row = conn.execute(
        "SELECT id, name FROM assets WHERE asset_type = 'pbr_set' AND deleted_at IS NULL"
    ).fetchone()
    assert set_row["name"] == "Bricks074"
    files = conn.execute(
        "SELECT rel_path, map_role, is_primary FROM files WHERE asset_id = ? "
        "ORDER BY map_role", (set_row["id"],),
    ).fetchall()
    assert {f["map_role"] for f in files} == {"basecolor", "normal", "roughness", "height"}
    capa = [f for f in files if f["is_primary"]]
    assert len(capa) == 1
    assert "Color" in capa[0]["rel_path"]  # capa = basecolor, como no brief


def test_sem_papel_anchor_nao_agrupa(env):
    conn, lib_id, _ = env
    apply_grouping(conn, lib_id)
    # duvida_Metal + duvida_Spec compartilham base 'duvida', mas sem âncora:
    nomes = {r["name"] for r in conn.execute(
        "SELECT name FROM assets WHERE deleted_at IS NULL AND name LIKE 'duvida%'"
    )}
    assert nomes == {"duvida_Metal", "duvida_Spec"}  # continuam separados


def test_agrupamento_e_idempotente(env):
    conn, lib_id, _ = env
    apply_grouping(conn, lib_id)
    depois = assets_repo.count_active(conn)

    stats2 = apply_grouping(conn, lib_id)

    assert stats2.sets_created == 0
    assert assets_repo.count_active(conn) == depois


def test_desagrupar_trava_contra_reagrupamento(env):
    conn, lib_id, _ = env
    apply_grouping(conn, lib_id)
    set_id = conn.execute(
        "SELECT id FROM assets WHERE asset_type = 'pbr_set' AND deleted_at IS NULL"
    ).fetchone()["id"]

    n = assets_repo.ungroup(conn, set_id)

    assert n == 4  # 4 assets individuais de volta
    stats = apply_grouping(conn, lib_id)
    assert stats.sets_created == 0  # travados: o agrupador respeita o Rafael


def test_agrupar_a_mao_funde_e_trava(env):
    conn, lib_id, _ = env
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM assets WHERE name IN ('gemeo_a', 'gemeo_b')"
    )]

    keeper = assets_repo.group_manual(conn, ids)

    assert keeper is not None
    row = conn.execute(
        "SELECT asset_type, group_locked FROM assets WHERE id = ?", (keeper,)
    ).fetchone()
    assert row["asset_type"] == "pbr_set"
    assert row["group_locked"] == 1
    n_files = conn.execute(
        "SELECT COUNT(*) AS n FROM files WHERE asset_id = ? AND deleted_at IS NULL",
        (keeper,),
    ).fetchone()["n"]
    assert n_files == 2


def test_rescan_apos_agrupamento_nao_desfaz_nada(env):
    conn, lib_id, root = env
    apply_grouping(conn, lib_id)
    antes = assets_repo.count_active(conn)

    stats = scan_library(conn, lib_id, root)  # revarredura completa

    assert stats.added == 0
    assert assets_repo.count_active(conn) == antes  # set continua set