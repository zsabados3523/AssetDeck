"""Loader de .blend via Blender headless (Fase 6). Mocka `export_to_obj`
e `blender_command` de propósito — mesma fronteira dos outros testes que
tocam Blender de verdade (`test_render.py`), pra não exigir Blender
instalado só pra rodar `pytest -q`. A integração real (Blender de
verdade exportando um .blend da testlib) foi verificada à mão, ver
TODO.md.
"""

from pathlib import Path

import pytest

from assetdeck.blender.render import RenderResult
from assetdeck.model3d import blend_loader
from assetdeck.model3d.obj_parser import MaterialRange, Mesh


@pytest.fixture(autouse=True)
def _manifesto_fake(monkeypatch):
    """O teste do cache não inicia o Blender só para gerar metadados."""
    def fake_manifest(_blend, obj, comando=None):
        target = obj.with_suffix(".materials.json")
        target.write_text("{}")
        return RenderResult(True, dest=target)
    monkeypatch.setattr(blend_loader, "export_material_manifest", fake_manifest)


def _obj_valido(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")


def test_sem_blender_levanta_runtimeerror_legivel(tmp_path, monkeypatch):
    monkeypatch.setattr(blend_loader, "blender_command", lambda: None)
    with pytest.raises(RuntimeError, match="Blender não encontrado"):
        blend_loader.load_via_blender(
            tmp_path / "modelo.blend", "hash123", tmp_path / "cache")


def test_exporta_e_le_quando_nao_tem_cache(tmp_path, monkeypatch):
    chamadas = []

    def _fake_export(blend_path, dest, comando=None):
        chamadas.append((blend_path, dest))
        _obj_valido(dest)
        return RenderResult(True, dest=dest)

    monkeypatch.setattr(blend_loader, "blender_command", lambda: ["blender"])
    monkeypatch.setattr(blend_loader, "export_to_obj", _fake_export)

    mesh = blend_loader.load_via_blender(
        tmp_path / "modelo.blend", "hash123", tmp_path / "cache")

    assert len(chamadas) == 1
    assert len(mesh.positions) == 3


def test_usa_cache_na_segunda_chamada_sem_chamar_o_blender_de_novo(tmp_path, monkeypatch):
    chamadas = []

    def _fake_export(blend_path, dest, comando=None):
        chamadas.append(dest)
        _obj_valido(dest)
        return RenderResult(True, dest=dest)

    monkeypatch.setattr(blend_loader, "blender_command", lambda: ["blender"])
    monkeypatch.setattr(blend_loader, "export_to_obj", _fake_export)

    cache_dir = tmp_path / "cache"
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash123", cache_dir)
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash123", cache_dir)

    assert len(chamadas) == 1  # só a primeira chamada exportou de verdade


def test_hash_diferente_reexporta(tmp_path, monkeypatch):
    """Conteúdo mudou (hash mudou) → não pode servir o .obj velho do cache."""
    chamadas = []

    def _fake_export(blend_path, dest, comando=None):
        chamadas.append(dest)
        _obj_valido(dest)
        return RenderResult(True, dest=dest)

    monkeypatch.setattr(blend_loader, "blender_command", lambda: ["blender"])
    monkeypatch.setattr(blend_loader, "export_to_obj", _fake_export)

    cache_dir = tmp_path / "cache"
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash-v1", cache_dir)
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash-v2", cache_dir)

    assert len(chamadas) == 2


def test_export_falhou_levanta_runtimeerror_com_o_motivo(tmp_path, monkeypatch):
    monkeypatch.setattr(blend_loader, "blender_command", lambda: ["blender"])
    monkeypatch.setattr(
        blend_loader, "export_to_obj",
        lambda *a, **k: RenderResult(False, erro="Error: cena vazia"),
    )
    with pytest.raises(RuntimeError, match="cena vazia"):
        blend_loader.load_via_blender(
            tmp_path / "modelo.blend", "hash123", tmp_path / "cache")


def test_manifesto_recupera_cor_e_textura_do_blend(tmp_path):
    imagem = tmp_path / "cor.png"
    imagem.write_bytes(b"imagem referenciada")
    manifesto = tmp_path / "modelo.materials.json"
    manifesto.write_text(
        '{"Mat": {"color": [0.2, 0.5, 0.7], "texture": "cor.png"}}')
    mesh = Mesh(positions=[(0, 0, 0)], normals=[(0, 0, 1)],
                materials=[MaterialRange(0, 1, name="Mat")])
    blend_loader._apply_manifest(mesh, manifesto, tmp_path / "modelo.blend")
    assert mesh.materials[0].color == pytest.approx((0.2, 0.5, 0.7))
    assert mesh.materials[0].texture == imagem


def test_manifesto_nao_refaz_exportacao_do_obj_cacheado(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    _obj_valido(blend_loader._cache_path(cache, "hash123"))
    monkeypatch.setattr(blend_loader, "export_to_obj", lambda *_: pytest.fail(
        "OBJ cacheado não deve ser exportado outra vez"))
    calls = []

    def fake_manifest(_blend, obj, comando=None):
        calls.append(obj)
        target = obj.with_suffix(".materials.json")
        target.write_text("{}")
        return RenderResult(True, dest=target)

    monkeypatch.setattr(blend_loader, "export_material_manifest", fake_manifest)
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash123", cache)
    blend_loader.load_via_blender(tmp_path / "modelo.blend", "hash123", cache)
    assert calls == [blend_loader._cache_path(cache, "hash123")]
