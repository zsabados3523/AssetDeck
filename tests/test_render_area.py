"""Setup da opção C: comportamento verificado dentro do Blender real."""

import subprocess

import pytest

from assetdeck.blender import render


@pytest.mark.skipif(render.blender_command() is None, reason="Blender não instalado")
def test_area_direcao_escala_e_energia(tmp_path):
    script = str(render.script_path())
    entrada_auto = str(tmp_path / "sem_luz.blend")
    saida_auto = str(tmp_path / "sem_luz.png")
    entrada_autoral = str(tmp_path / "luz_autoral.blend")
    saida_autoral = str(tmp_path / "luz_autoral.png")

    codigo_auto = f'''
import math
import runpy
import sys
from pathlib import Path
import bpy
from mathutils import Vector

ns = runpy.run_path({script!r})
ns["AMOSTRAS_CYCLES"] = 1
cena = bpy.context.scene
for obj in list(cena.objects):
    if obj.type == "LIGHT":
        bpy.data.objects.remove(obj, do_unlink=True)
cubo = next(obj for obj in cena.objects if obj.type == "MESH")
cena.camera.rotation_euler = (ns["DIRECAO_CAMERA"] * -1).to_track_quat("-Z", "Y").to_euler()
bpy.context.view_layer.update()
centro, raio = ns["caixa_da_cena"]([cubo])
luz = ns["_nova_area"](cena, [cubo], 3.0)
assert luz.data.type == "AREA" and luz.data.shape == "DISK"
assert abs(luz.data.size - raio) < 1e-5
assert abs(luz.data.energy - 120 * (raio * 2)**2) < 1e-3
v = luz.location - centro
assert abs(v.length - raio * 4) < 1e-5
assert abs(math.degrees(math.atan2(v.z, math.hypot(v.x, v.y))) - 40) < 1e-4
cam_dir = ns["DIRECAO_CAMERA"]
assert abs(math.degrees(math.atan2(v.y, v.x) - math.atan2(cam_dir.y, cam_dir.x)) - 45) < 1e-4
mirada = luz.rotation_euler.to_quaternion() @ Vector((0, 0, -1))
assert mirada.normalized().dot((centro - luz.location).normalized()) > 0.99999

potencia, tamanho, distancia = luz.data.energy, luz.data.size, v.length
bpy.data.objects.remove(luz, do_unlink=True)
cubo.scale *= 10
bpy.context.view_layer.update()
luz = ns["_nova_area"](cena, [cubo], 3.0)
assert abs(luz.data.energy / potencia - 100) < 1e-3
assert abs(luz.data.size / tamanho - 10) < 1e-4
assert abs((luz.location - centro).length / distancia - 10) < 1e-4
bpy.data.objects.remove(luz, do_unlink=True)
luz = ns["_nova_area"](cena, [cubo], 6.0)
assert abs(luz.data.energy / potencia - 200) < 1e-3
bpy.data.objects.remove(luz, do_unlink=True)
cena.camera.rotation_euler.z += math.pi / 2
luz = ns["_nova_area"](cena, [cubo], 3.0)
v2 = (luz.location - centro).normalized()
rotacionado = Vector((-v.y, v.x, v.z)).normalized()
assert v2.dot(rotacionado) > 0.99999
bpy.data.objects.remove(luz, do_unlink=True)

entrada, saida = {entrada_auto!r}, {saida_auto!r}
bpy.ops.wm.save_as_mainfile(filepath=entrada)
sys.argv = ["blender", "--", entrada, saida, "32"]
ns["main"]()
cena = bpy.context.scene
assert Path(saida).is_file()
luzes = [obj for obj in cena.objects if obj.type == "LIGHT"]
assert len(luzes) == 1 and luzes[0].data.type == "AREA"
assert cena.world.node_tree.nodes.get("Background").inputs[1].default_value == 1.0
assert cena.render.image_settings.file_format == "PNG"
assert cena.render.image_settings.color_mode == "RGBA"
assert cena.render.film_transparent
malhas = [obj for obj in cena.objects if obj.type == "MESH"]
assert len(malhas) == 1 and malhas[0].name == "Cube"
assert not malhas[0].is_shadow_catcher
print("AREA_AUTO_TEST_OK")
# Evita o bloqueio do loop de interface ao encerrar Blender headless no sandbox;
# todas as verificações e o render já terminaram.
sys.stdout.flush()
import os
os._exit(0)
'''

    codigo_luz_autoral = f'''
import runpy
import sys
from pathlib import Path
import bpy

ns = runpy.run_path({script!r})
ns["AMOSTRAS_CYCLES"] = 1
cena = bpy.context.scene
for obj in list(cena.objects):
    if obj.type == "LIGHT":
        bpy.data.objects.remove(obj, do_unlink=True)
luz_data = bpy.data.lights.new("LuzAutoral", type="POINT")
luz_data.energy = 123.0
luz = bpy.data.objects.new("LuzAutoral", luz_data)
cena.collection.objects.link(luz)
entrada, saida = {entrada_autoral!r}, {saida_autoral!r}
bpy.ops.wm.save_as_mainfile(filepath=entrada)
sys.argv = ["blender", "--", entrada, saida, "32"]
ns["main"]()
luzes = [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT"]
assert Path(saida).is_file()
assert len(luzes) == 1
assert luzes[0].data.type == "POINT" and luzes[0].data.energy == 123.0
print("AREA_AUTHORED_LIGHT_TEST_OK")
# Todas as verificações e o render já terminaram.
sys.stdout.flush()
import os
os._exit(0)
'''

    comando = render.blender_command()
    assert comando is not None
    for codigo, marcador in (
        (codigo_auto, "AREA_AUTO_TEST_OK"),
        (codigo_luz_autoral, "AREA_AUTHORED_LIGHT_TEST_OK"),
    ):
        proc = subprocess.run(
            [*comando, "-b", "-t", "1", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "1", "--python-expr", codigo],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert marcador in proc.stdout
