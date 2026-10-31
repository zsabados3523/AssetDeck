"""Executado pelo Blender headless para renderizar uma esfera com um set PBR."""

import importlib.util
import json
import os
import sys
import traceback

import bpy
from mathutils import Vector


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    materials_path, dest, name, size_arg, maps_json = args
    size = int(size_arg)
    spec = importlib.util.spec_from_file_location("assetdeck_materials", materials_path)
    materials = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(materials)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32)
    sphere = bpy.context.object
    sphere.name = "Material preview"
    for polygon in sphere.data.polygons:
        polygon.use_smooth = True
    sphere.data.materials.append(materials.build_material(name, json.loads(maps_json)))

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12 if size > 256 else 24
    scene.view_layers[0].cycles.use_denoising = True
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = dest

    world = bpy.data.worlds.new("Material preview world")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.4
    scene.world = world

    camera_data = bpy.data.cameras.new("Material preview camera")
    camera = bpy.data.objects.new("Material preview camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (2.8, -4.2, 2.3)
    camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2.5
    scene.camera = camera

    for name, location, energy, size in (
        ("Key", (2.5, -3, 4), 550, 3.0),
        ("Fill", (-3, -1, 1.5), 250, 3.0),
        ("Rim", (1, 3, 3), 700, 2.0),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (-light.location).to_track_quat("-Z", "Y").to_euler()

    bpy.ops.render.render(write_still=True)


try:
    main()
except Exception:
    traceback.print_exc()
    os._exit(1)
os._exit(0)
