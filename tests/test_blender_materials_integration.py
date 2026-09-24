"""Regressão do material PBR executada no Blender real, quando instalado."""

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from PIL import Image


def test_reaplicar_set_preserva_material_anterior(tmp_path):
    blender = shutil.which("blender")
    if blender is None:
        pytest.skip("Blender não instalado")

    mapa = tmp_path / "cor.png"
    Image.new("RGB", (2, 2), (180, 100, 60)).save(mapa)
    materials_path = Path(__file__).parents[1] / "blender_addon/assetdeck_bridge/materials.py"
    project_root = Path(__file__).parents[1]
    script = tmp_path / "verificar_material.py"
    script.write_text(textwrap.dedent(f"""
        import importlib.util
        import os
        import sys
        import traceback
        import bpy

        try:
            spec = importlib.util.spec_from_file_location(
                "assetdeck_materials", {str(materials_path)!r}
            )
            materials = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(materials)

            mapas = {{"basecolor": {str(mapa)!r}, "opacity": {str(mapa)!r}}}
            primeiro = materials.build_material("Teste", mapas)
            primeiro_grupo = next(n.node_tree for n in primeiro.node_tree.nodes
                                   if n.type == "GROUP")
            segundo = materials.build_material("Teste", mapas)
            segundo_grupo = next(n.node_tree for n in segundo.node_tree.nodes
                                  if n.type == "GROUP")

            assert primeiro_grupo != segundo_grupo
            assert primeiro_grupo.name in bpy.data.node_groups
            assert any(n.type == "TEX_IMAGE" for n in primeiro_grupo.nodes)
            assert any(n.type == "TEX_IMAGE" for n in segundo_grupo.nodes)
            assert any(n.type == "BSDF_PRINCIPLED" for n in primeiro.node_tree.nodes)

            sys.path.insert(0, {str(project_root)!r})
            from blender_addon.assetdeck_bridge import client, drops
            drops.register()
            bpy.ops.mesh.primitive_cube_add()
            cubo = bpy.context.active_object
            client.request = lambda _payload: {{
                "asset": {{"name": "Teste Drag", "asset_type": "pbr_set"}},
                "files": [{{"path": {str(mapa)!r}, "map_role": "basecolor"}}],
            }}
            assert bpy.ops.assetdeck.drop_texture(filepath={str(mapa)!r}) == {{"FINISHED"}}
            aplicado = cubo.data.materials[0]
            assert aplicado.name.startswith("AD_Teste Drag")

            client.request = lambda _payload: {{
                "asset": {{"name": "Teste Quebrado", "asset_type": "pbr_set"}},
                "files": [{{"path": "/arquivo/inexistente.png", "map_role": "basecolor"}}],
            }}
            try:
                bpy.ops.assetdeck.drop_texture(filepath={str(mapa)!r})
            except RuntimeError as exc:
                assert "Falha ao montar o material" in str(exc)
            else:
                raise AssertionError("Mapa ausente deveria impedir a aplicação")
            assert cubo.data.materials[0] == aplicado
            print("MATERIAL_PBR_OK", flush=True)
            os._exit(0)
        except Exception:
            traceback.print_exc()
            os._exit(1)
    """), encoding="utf-8")

    result = subprocess.run(
        [blender, "-b", "-t", "1", "--factory-startup", "--python", str(script)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0 and "MATERIAL_PBR_OK" in result.stdout, (
        result.stdout + result.stderr
    )
