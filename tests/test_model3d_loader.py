"""Dispatcher de loader por extensão (Fase 6)."""

from pathlib import Path

import pytest

from assetdeck.model3d import loader


def test_obj_vai_pro_parser_caseiro(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(loader, "parse_obj", lambda p: chamadas.append(p) or "mesh-obj")
    resultado = loader.load_mesh(tmp_path / "modelo.obj")
    assert resultado == "mesh-obj"
    assert chamadas == [tmp_path / "modelo.obj"]


def test_fbx_vai_pro_loader_de_assimp(tmp_path, monkeypatch):
    import assetdeck.model3d.assimp_loader as assimp_loader

    chamadas = []
    monkeypatch.setattr(assimp_loader, "load_via_assimp",
                        lambda p: chamadas.append(p) or "mesh-fbx")
    resultado = loader.load_mesh(tmp_path / "modelo.fbx")
    assert resultado == "mesh-fbx"
    assert chamadas == [tmp_path / "modelo.fbx"]


def test_blend_vai_pro_loader_do_blender_com_content_hash(tmp_path, monkeypatch):
    import assetdeck.model3d.blend_loader as blend_loader

    chamadas = []
    monkeypatch.setattr(
        blend_loader, "load_via_blender",
        lambda path, content_hash, cache_dir: chamadas.append(
            (path, content_hash)) or "mesh-blend",
    )
    resultado = loader.load_mesh(tmp_path / "modelo.blend", content_hash="abc123")
    assert resultado == "mesh-blend"
    assert chamadas == [(tmp_path / "modelo.blend", "abc123")]


def test_blend_sem_content_hash_levanta_valueerror(tmp_path):
    with pytest.raises(ValueError, match="content_hash"):
        loader.load_mesh(tmp_path / "modelo.blend")


def test_extensao_desconhecida_levanta_valueerror(tmp_path):
    with pytest.raises(ValueError, match=r"\.stl"):
        loader.load_mesh(tmp_path / "modelo.stl")


def test_extensoes_suportadas_bate_com_o_que_o_dispatcher_trata():
    assert set(loader.EXTENSOES_SUPORTADAS) == {".obj", ".fbx", ".blend"}
