"""Exporta OBJ/MTL e metadados de materiais de um .blend para o cache.

Argumentos após ``--``: ``<modelo.blend> <cache.obj> [--manifest-only]``.
O modo de manifesto reaproveita o OBJ já exportado. Nunca escreve na
biblioteca de origem, inclusive quando uma imagem está empacotada.
"""

import hashlib
import json
import os
from pathlib import Path
import sys

import bpy


def _linked_images(socket, visited):
    """Segue a entrada de cor por ajustes/misturas até as imagens usadas."""
    result = []
    for link in socket.links:
        node = link.from_node
        key = node.as_pointer()
        if key in visited:
            continue
        visited.add(key)
        if node.type == 'TEX_IMAGE' and node.image is not None:
            result.append(node.image)
            continue
        for entry in node.inputs:
            if entry.is_linked and entry.type in {'RGBA', 'VECTOR', 'VALUE'}:
                result.extend(_linked_images(entry, visited))
    return result


def _image_score(image):
    name = (image.filepath or image.name).lower()
    good = ('base_color', 'basecolor', 'albedo', 'diffuse', 'color', 'colour')
    bad = ('normal', 'rough', 'gloss', 'metal', 'height', 'bump',
           'opacity', 'alpha', 'specular', 'displace')
    return sum(5 for term in good if term in name) - sum(20 for term in bad if term in name)


def _named_color_images(tree, visited):
    if tree.as_pointer() in visited:
        return []
    visited.add(tree.as_pointer())
    result = []
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image is not None:
            if _image_score(node.image) > 0:
                result.append(node.image)
        elif node.type == 'GROUP' and node.node_tree is not None:
            result.extend(_named_color_images(node.node_tree, visited))
    return result


def _base_color(mat):
    if not mat.use_nodes or not mat.node_tree:
        return tuple(mat.diffuse_color[:3]), None

    shaders = [node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED']
    images = []
    for shader in shaders:
        base = shader.inputs.get('Base Color')
        if base is not None:
            images.extend(_linked_images(base, set()))
    if not images:
        # Alguns grupos customizados escondem a ligação ao Principled.
        # Nesse caso só aceita uma imagem com nome claramente de cor.
        images = _named_color_images(mat.node_tree, set())
    if images:
        best = max(images, key=_image_score)
        return (1.0, 1.0, 1.0), best

    if shaders:
        base = shaders[0].inputs.get('Base Color')
        if base is not None and not base.is_linked:
            return tuple(base.default_value[:3]), None
    return tuple(mat.diffuse_color[:3]), None


def _image_path(image, obj_path):
    source = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
    if source is not None and source.is_file():
        return str(source)
    if image.packed_file is not None:
        folder = obj_path.parent / f'{obj_path.stem}-images'
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(image.name.encode('utf-8')).hexdigest()[:12]
        suffix = source.suffix if source and source.suffix else '.png'
        target = folder / f'{digest}{suffix}'
        if not target.is_file():
            target.write_bytes(bytes(image.packed_file.data))
        return str(target)
    if source is not None:
        # O leitor tenta os dois diretórios vizinhos; caminho faltante é
        # registrado no log do app se também não estiver lá.
        return str(source)
    print(f'Imagem sem caminho e sem dados empacotados: {image.name}', file=sys.stderr)
    return None


def _write_manifest(obj_path):
    result = {}
    for mat in bpy.data.materials:
        if not mat.users:
            continue
        color, image = _base_color(mat)
        name = bpy.path.clean_name(mat.name)
        result[name] = {
            'color': [float(c) for c in color],
            'texture': _image_path(image, obj_path) if image is not None else None,
        }
    target = obj_path.with_suffix('.materials.json')
    temporary = Path(f'{target}.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temporary.replace(target)


args = sys.argv[sys.argv.index('--') + 1:]
if len(args) not in (2, 3) or (len(args) == 3 and args[2] != '--manifest-only'):
    raise SystemExit('Uso: export_obj.py -- <modelo.blend> <cache.obj> [--manifest-only]')

blend_path, obj_path = args[:2]
obj_path = Path(obj_path)
bpy.ops.wm.open_mainfile(filepath=blend_path)
if len(args) == 2:
    bpy.ops.wm.obj_export(filepath=str(obj_path), export_materials=True,
                          export_uv=True, path_mode='ABSOLUTE')
_write_manifest(obj_path)

# Em alguns ambientes headless o Blender termina o script, mas fica preso
# ao desligar o subsistema de áudio. Os arquivos acima já foram fechados.
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
