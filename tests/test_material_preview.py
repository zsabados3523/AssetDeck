"""Capas PBR: cache, render no Blender e prioridade no grid."""

import shutil
import time

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from assetdeck.blender.material_preview import (
    preview_key, preview_path, render_material_preview,
)
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.grouper import apply_grouping
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.pipeline import ThumbnailPipeline
from assetdeck.ui.asset_grid import AssetGridModel


def test_chave_muda_com_qualquer_mapa():
    files = [{"map_role": "basecolor", "content_hash": "cor-1"},
             {"map_role": "normal", "content_hash": "normal-1"}]
    original = preview_key(files)
    assert preview_key(list(reversed(files))) == original
    files[1]["content_hash"] = "normal-2"
    assert preview_key(files) != original


def test_blender_renderiza_material_em_png(tmp_path):
    if shutil.which("blender") is None:
        pytest.skip("Blender não instalado")
    color = tmp_path / "color.png"
    Image.new("RGB", (16, 16), (170, 80, 45)).save(color)
    dest = tmp_path / "thumbs" / "material.png"

    render_material_preview("Material de teste", {"basecolor": color}, dest)

    with Image.open(dest) as img:
        assert img.size == (256, 256)
        assert img.mode == "RGBA"
        assert img.getpixel((128, 128))[3] == 255  # esfera visível
        assert img.getpixel((0, 0))[3] == 0  # fundo transparente
    assert color.exists()  # mapa de origem intocado


def test_pipeline_avisa_quando_capa_pbr_fica_pronta(qapp, tmp_path):
    if shutil.which("blender") is None:
        pytest.skip("Blender não instalado")
    color = tmp_path / "color.png"
    Image.new("RGB", (16, 16), (170, 80, 45)).save(color)
    pipeline = ThumbnailPipeline(tmp_path / "thumbs")
    ready = []
    pipeline.ready.connect(lambda aid, path: ready.append((aid, path)))
    key = preview_key([{"map_role": "basecolor", "content_hash": "teste"}])
    dest = preview_path(tmp_path / "thumbs", key, size=640)
    try:
        assert pipeline.get_or_request_material(
            7, "Teste", {"basecolor": color}, key, size=640, priority=2) is None
        deadline = time.monotonic() + 30
        while not ready and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
        assert ready == [(7, str(dest))]
        assert dest.is_file()
        with Image.open(dest) as image:
            assert image.size == (640, 640)
        assert pipeline.get_or_request_material(
            7, "Teste", {"basecolor": color}, key, size=640) == dest
    finally:
        pipeline.shutdown()


def test_grid_usa_capa_pbr_e_respeita_capa_manual(qapp, tmp_path, monkeypatch):
    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (16, 16), (130, 80, 50)).save(root / "Stone_Color.png")
    Image.new("L", (16, 16), 120).save(root / "Stone_Roughness.png")
    db = connect(tmp_path / "test.db")
    apply_migrations(db)
    lib_id = libraries_repo.get_or_create(db, root)
    scan_library(db, lib_id, root)
    apply_grouping(db, lib_id)
    asset_id = db.execute(
        "SELECT id FROM assets WHERE asset_type = 'pbr_set' AND deleted_at IS NULL"
    ).fetchone()["id"]

    generated = tmp_path / "generated.png"
    Image.new("RGB", (256, 256), (200, 30, 20)).save(generated)
    manual = tmp_path / "manual.png"
    Image.new("RGB", (256, 256), (20, 30, 200)).save(manual)

    pipeline = ThumbnailPipeline(tmp_path / "thumbs")
    requested = []
    generated_ready = False

    def material_result(aid, name, maps, key):
        requested.append((aid, set(maps)))
        return generated if generated_ready else None

    monkeypatch.setattr(
        pipeline, "get_or_request_material", material_result,
    )
    monkeypatch.setattr(pipeline, "get_or_request",
                        lambda *_args, **_kwargs: root / "Stone_Color.png")
    model = AssetGridModel(db, root, pipeline)
    try:
        model.reload()
        pix = model.data(model.index_of_asset(asset_id), Qt.ItemDataRole.DecorationRole)
        assert pix.toImage().pixelColor(80, 80).red() == 130

        generated_ready = True
        pix = model.data(model.index_of_asset(asset_id), Qt.ItemDataRole.DecorationRole)
        assert pix.toImage().pixelColor(80, 80).red() == 200
        assert requested == [(asset_id, {"basecolor", "roughness"})] * 2

        previews_repo.add(db, asset_id, manual, tmp_path / "previews")
        monkeypatch.setattr(pipeline, "get_or_request",
                            lambda *_args, **_kwargs: manual)
        model.reload()
        pix = model.data(model.index_of_asset(asset_id), Qt.ItemDataRole.DecorationRole)
        assert pix.toImage().pixelColor(80, 80).blue() == 200
        assert len(requested) == 2
    finally:
        pipeline.shutdown()
        db.close()
