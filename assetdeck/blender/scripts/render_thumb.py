"""Roda DENTRO do Blender (blender -b -P) para renderizar a capa de um modelo.

Recebe, depois de '--':
  <arquivo.blend> <saida.png> [tamanho] [bg_r bg_g bg_b bg_strength sun_energy]

Os 5 últimos (cena configurável, Fatia 38) são opcionais — sem eles, cai
nos mesmos valores que sempre foram hardcoded aqui, então chamar este
script à mão continua funcionando igual.

Enquadra tudo que é visível numa câmera automática, ilumina com um céu
neutro e renderiza. Se o .blend já tiver câmera própria, ela é respeitada —
o autor do asset costuma ter enquadrado melhor do que qualquer heurística.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

MARGEM = 1.05  # folga em volta do objeto
NIVEIS_BUSCA = 2  # quantas pastas subir procurando texturas perdidas

# Mesmos valores que sempre foram hardcoded — viram o fallback quando o
# script roda sem os argumentos de cena (chamado à mão, ou versão antiga
# de assetdeck/blender/render.py chamando este script).
BG_COLOR_PADRAO = (0.30, 0.30, 0.32)
BG_STRENGTH_PADRAO = 1.8
SUN_ENERGY_PADRAO = 3.0


def texturas_perdidas():
    return [img for img in bpy.data.images
            if img.filepath and img.source == "FILE"
            and not os.path.isfile(bpy.path.abspath(img.filepath))]


def relocalizar_texturas(blend_path):
    """Procura texturas cujo caminho no .blend não resolve.

    Packs comerciais frequentemente vêm com caminhos quebrados (o Maxtree
    aponta para uma subpasta quando os mapas estão numa pasta IRMÃ). Sem
    isso o modelo renderiza magenta. Só a cópia em memória é ajustada —
    o arquivo do usuário nunca é alterado.
    """
    perdidas = texturas_perdidas()
    if not perdidas:
        return 0
    base = os.path.dirname(os.path.abspath(blend_path))
    for _ in range(NIVEIS_BUSCA):
        base = os.path.dirname(base)
        try:
            bpy.ops.file.find_missing_files(directory=base)
        except Exception as exc:  # noqa: BLE001 — nunca derruba o render
            print("ASSETDECK_AVISO relocalizacao falhou:", exc, flush=True)
            break
        if not texturas_perdidas():
            break
    recuperadas = len(perdidas) - len(texturas_perdidas())
    print(f"ASSETDECK_TEXTURAS perdidas={len(perdidas)} recuperadas={recuperadas}",
          flush=True)
    return recuperadas


def argumentos():
    if "--" not in sys.argv:
        raise SystemExit(
            "Uso: blender -b -P render_thumb.py -- entrada.blend saida.png "
            "[px] [bg_r bg_g bg_b bg_strength sun_energy]"
        )
    resto = sys.argv[sys.argv.index("--") + 1:]
    if len(resto) < 2:
        raise SystemExit("Faltam argumentos: entrada.blend saida.png")
    entrada, saida = resto[0], resto[1]
    tamanho = int(resto[2]) if len(resto) > 2 else 512
    if len(resto) > 7:
        bg_color = (float(resto[3]), float(resto[4]), float(resto[5]))
        bg_strength = float(resto[6])
        sun_energy = float(resto[7])
    else:
        bg_color, bg_strength, sun_energy = (
            BG_COLOR_PADRAO, BG_STRENGTH_PADRAO, SUN_ENERGY_PADRAO)
    return entrada, saida, tamanho, bg_color, bg_strength, sun_energy


def caixa_da_cena(objetos):
    """(centro, raio) que engloba todos os objetos visíveis."""
    cantos = []
    for obj in objetos:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        for canto in obj.bound_box:
            cantos.append(obj.matrix_world @ Vector(canto))
    if not cantos:
        return Vector((0, 0, 0)), 1.0
    minimo = Vector((min(c.x for c in cantos), min(c.y for c in cantos),
                     min(c.z for c in cantos)))
    maximo = Vector((max(c.x for c in cantos), max(c.y for c in cantos),
                     max(c.z for c in cantos)))
    centro = (minimo + maximo) / 2.0
    raio = max((maximo - minimo).length / 2.0, 1e-3)
    return centro, raio


def main():
    entrada, saida, tamanho, bg_color, bg_strength, sun_energy = argumentos()
    bpy.ops.wm.open_mainfile(filepath=entrada)
    relocalizar_texturas(entrada)
    cena = bpy.context.scene

    visiveis = [o for o in cena.objects if not o.hide_render]
    if not visiveis:
        raise SystemExit("Nada visível para renderizar neste .blend")

    if cena.camera is None:
        centro, raio = caixa_da_cena(visiveis)
        cam_data = bpy.data.cameras.new("AD_Cam")
        cam = bpy.data.objects.new("AD_Cam", cam_data)
        cena.collection.objects.link(cam)
        cena.camera = cam
        # Três quartos, ligeiramente acima — enquadramento clássico de catálogo
        direcao = Vector((1.0, -1.2, 0.75)).normalized()
        # Distância exata para uma esfera de `raio` caber no campo de visão
        # (antes era um múltiplo chutado, e o objeto ficava pequeno no quadro)
        meio_angulo = cam_data.angle / 2.0
        distancia = (raio * MARGEM) / max(math.sin(meio_angulo), 1e-3)
        cam.location = centro + direcao * distancia
        cam.rotation_euler = (direcao * -1).to_track_quat("-Z", "Y").to_euler()
        cam_data.clip_start = max(raio * 0.01, 0.001)
        cam_data.clip_end = raio * 100.0

    # World NOVO sempre: o do arquivo pode ser um céu escuro ou um HDRI
    # pesado, e as capas da biblioteca precisam ser consistentes entre si.
    mundo = bpy.data.worlds.new("AD_World")
    mundo.use_nodes = True
    cena.world = mundo
    nodes, links = mundo.node_tree.nodes, mundo.node_tree.links
    nodes.clear()
    fundo = nodes.new("ShaderNodeBackground")
    fundo.inputs[0].default_value = (*bg_color, 1.0)
    fundo.inputs[1].default_value = bg_strength
    saida_mundo = nodes.new("ShaderNodeOutputWorld")
    links.new(fundo.outputs["Background"], saida_mundo.inputs["Surface"])

    if not any(o.type == "LIGHT" for o in visiveis):
        luz_data = bpy.data.lights.new("AD_Sun", type="SUN")
        luz_data.energy = sun_energy
        luz = bpy.data.objects.new("AD_Sun", luz_data)
        cena.collection.objects.link(luz)
        luz.rotation_euler = (0.9, 0.2, 0.6)

    cena.render.engine = "BLENDER_EEVEE"  # rápido; qualidade suficiente p/ capa
    cena.render.resolution_x = cena.render.resolution_y = tamanho
    cena.render.resolution_percentage = 100
    cena.render.film_transparent = False
    cena.render.image_settings.file_format = "PNG"
    cena.render.filepath = saida
    bpy.ops.render.render(write_still=True)
    print("ASSETDECK_RENDER_OK", saida, flush=True)


main()
