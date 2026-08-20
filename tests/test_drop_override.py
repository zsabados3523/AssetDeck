"""Fatia 97 — soltar um .blend em modo Link tem que guardar a posição.

O bug: o add-on embrulhava os objetos linkados num Empty local e gravava
`obj.parent` no datablock LINKADO. Esse datablock pertence ao arquivo da
biblioteca, então o parentesco não era salvo no arquivo do usuário — ao
reabrir, o objeto voltava pro centro da cena.

Só o Blender de verdade prova isso: o comportamento está em salvar e
reabrir um .blend, não em lógica Python que dá pra simular.
"""

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from assetdeck.blender.render import blender_command

ADDON_DIR = Path(__file__).resolve().parent.parent / "blender_addon"

pytestmark = pytest.mark.skipif(
    blender_command() is None, reason="Blender não encontrado nesta máquina"
)


def _roda(script: str, *args: str) -> dict:
    """Executa `script` num Blender headless e devolve o JSON impresso."""
    cmd = [*blender_command(), "-b", "-noaudio", "--factory-startup",
           "--python-expr", textwrap.dedent(script), "--", *args]
    saida = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    for linha in saida.stdout.splitlines():
        if linha.startswith("RESULTADO_JSON="):
            return json.loads(linha.split("=", 1)[1])
    raise AssertionError(
        f"script não devolveu resultado.\nstdout:\n{saida.stdout}\n"
        f"stderr:\n{saida.stderr}"
    )


CRIA_ASSET = """
    import bpy, sys
    destino = sys.argv[sys.argv.index("--") + 1:][0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    malha = bpy.data.meshes.new("MalhaDoTeste")
    import bmesh
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(malha); bm.free()
    obj = bpy.data.objects.new("CuboDoTeste", malha)
    bpy.context.collection.objects.link(obj)
    bpy.ops.wm.save_as_mainfile(filepath=destino)
    print("RESULTADO_JSON=" + '{"ok": true}')
"""

SOLTA_E_REABRE = """
    import bpy, json, sys, mathutils
    argv = sys.argv[sys.argv.index("--") + 1:]
    addon_dir, asset, cena = argv[0], argv[1], argv[2]
    sys.path.insert(0, addon_dir)
    from assetdeck_bridge import importer
    importer.register()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.assetdeck.import_blend(
        filepath=asset, datablock="objects", link=True, place=False)

    alvo = [o for o in bpy.context.collection.objects][0]
    alvo.location = mathutils.Vector((5.0, 3.0, 1.0))
    bpy.ops.wm.save_as_mainfile(filepath=cena)

    bpy.ops.wm.open_mainfile(filepath=cena)
    objs = list(bpy.context.scene.collection.all_objects)
    r = {
        "quantidade": len(objs),
        "posicao": [round(v, 2) for v in objs[0].matrix_world.translation],
        "eh_override": bool(objs[0].override_library),
        "ainda_linkado": len(bpy.data.libraries) > 0,
        "tipos": sorted(o.type for o in objs),
    }
    print("RESULTADO_JSON=" + json.dumps(r))
"""


@pytest.fixture
def asset(tmp_path):
    caminho = tmp_path / "CuboDoTeste.blend"
    _roda(CRIA_ASSET, str(caminho))
    assert caminho.is_file()
    return caminho


def test_posicao_sobrevive_ao_reabrir(asset, tmp_path):
    """O que o Rafael via: móvel voltava pro centro depois de reabrir."""
    r = _roda(SOLTA_E_REABRE, str(ADDON_DIR), str(asset),
              str(tmp_path / "cena.blend"))
    assert r["posicao"] == [5.0, 3.0, 1.0], (
        "a posição não sobreviveu ao salvar/reabrir — voltou pro centro"
    )


def test_vira_override_e_nao_copia_a_malha(asset, tmp_path):
    """Override em vez de Append: edita a posição sem inchar o arquivo."""
    r = _roda(SOLTA_E_REABRE, str(ADDON_DIR), str(asset),
              str(tmp_path / "cena.blend"))
    assert r["eh_override"] is True, "deveria ser Library Override"
    assert r["ainda_linkado"] is True, (
        "a malha deveria continuar na biblioteca, não copiada pra dentro"
    )


def test_nao_deixa_objeto_duplicado_nem_empty_orfao(asset, tmp_path):
    """O Empty do jeito antigo sobrava na cena sem nada preso nele."""
    r = _roda(SOLTA_E_REABRE, str(ADDON_DIR), str(asset),
              str(tmp_path / "cena.blend"))
    assert r["quantidade"] == 1, f"esperava 1 objeto, veio {r['tipos']}"
    assert "EMPTY" not in r["tipos"], "sobrou um Empty órfão na cena"
