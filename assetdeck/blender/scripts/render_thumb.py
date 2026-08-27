"""Roda DENTRO do Blender (blender -b -P) para renderizar a capa de um modelo.

Recebe, depois de '--':
  <arquivo.blend> <saida.png> [tamanho] [bg_r bg_g bg_b bg_strength sun_energy]

Os 5 últimos (cena configurável, Fatia 38) são opcionais — sem eles, cai
nos mesmos valores que sempre foram hardcoded aqui, então chamar este
script à mão continua funcionando igual. Os NOMES ficaram do jeito que
sempre foram (a assinatura pública de `render_thumbnail()` não mudou), mas
o SIGNIFICADO mudou na Fatia 102: `bg_color`/`bg_strength` viraram a luz
AMBIENTE (o fundo não é mais visível — é transparente), e `sun_energy`
virou a intensidade da luz KEY do setup de 3 pontos.

Enquadra tudo que é visível numa câmera automática. Se o .blend já tiver
câmera própria, ela é respeitada — o autor do asset costuma ter enquadrado
melhor do que qualquer heurística. Mesma lógica pra luz: um .blend com luz
própria mantém a dele; sem nenhuma, entra o setup de 3 pontos (Fatia 102,
pedido do Rafael: "acho que ficaria melhor e daria pra ver melhor o
asset") — key/fill/rim nas mesmas três direções relativas à câmera sempre,
pra ficar previsível na biblioteca inteira.

Renderiza em CYCLES (Fatia 102, pedido explícito — antes era EEVEE), fundo
TRANSPARENTE (`film_transparent`), com poucas amostras e denoise: rápido o
bastante pra fila de capas (medido: ~3-8s por modelo nesta máquina, contra
os ~180s de limite por item) e sem o ruído característico de Cycles em
poucas amostras.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

MARGEM = 1.05  # folga em volta do objeto
NIVEIS_BUSCA = 2  # quantas pastas subir procurando texturas perdidas

# Mesma direção da câmera automática (três quartos, ligeiramente acima) —
# as três luzes são calculadas a partir dela, então a relação luz-câmera
# fica sempre a mesma, em qualquer .blend da biblioteca.
DIRECAO_CAMERA = Vector((1.0, -1.2, 0.75)).normalized()

# Frações da energia da KEY — proporção clássica de um 3-point lighting
# (fill mais fraca que a key pra não apagar a sombra; rim intermediária,
# só pra separar a silhueta do fundo transparente).
FRACAO_FILL = 0.45
FRACAO_RIM = 0.65
AMOSTRAS_CYCLES = 64  # suficiente com denoise pra uma capa de catálogo

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


def _girar_z(v, graus):
    """Gira `v` em torno do eixo Z do mundo — usado pra espalhar fill e rim
    em volta da key, sem precisar pensar em ângulos absolutos."""
    ang = math.radians(graus)
    return Vector((v.x * math.cos(ang) - v.y * math.sin(ang),
                   v.x * math.sin(ang) + v.y * math.cos(ang), v.z))


def _nova_sun(cena, nome, direcao_de_onde_vem, energia):
    """Sun apontando pro centro da cena a partir de `direcao_de_onde_vem` —
    mesma técnica (`to_track_quat`) já usada pra mirar a câmera automática."""
    luz_data = bpy.data.lights.new(nome, type="SUN")
    luz_data.energy = energia
    luz_data.angle = math.radians(6)  # penumbra suave, não sombra de navalha
    luz = bpy.data.objects.new(nome, luz_data)
    cena.collection.objects.link(luz)
    luz.rotation_euler = (
        direcao_de_onde_vem * -1).to_track_quat("-Z", "Y").to_euler()
    return luz


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
        # Distância exata para uma esfera de `raio` caber no campo de visão
        # (antes era um múltiplo chutado, e o objeto ficava pequeno no quadro)
        meio_angulo = cam_data.angle / 2.0
        distancia = (raio * MARGEM) / max(math.sin(meio_angulo), 1e-3)
        cam.location = centro + DIRECAO_CAMERA * distancia
        cam.rotation_euler = (DIRECAO_CAMERA * -1).to_track_quat("-Z", "Y").to_euler()
        cam_data.clip_start = max(raio * 0.01, 0.001)
        cam_data.clip_end = raio * 100.0

    # World NOVO sempre: o do arquivo pode ser um céu escuro ou um HDRI
    # pesado, e as capas da biblioteca precisam ser consistentes entre si.
    #
    # Fatia 102 (Rafael: "teria como deixar o fundo transparente?"): o fundo
    # deixou de aparecer no PNG (`film_transparent`, mais abaixo), mas o
    # World continua existindo — sua força ilumina a cena inteira por igual
    # (GI ambiente) mesmo invisível, então zerá-lo deixaria sombra e reflexo
    # duros demais. `bg_strength` virou essa luz de preenchimento AMBIENTE,
    # bem mais sutil do que quando era "cor de fundo visível" — daí o 0.15.
    mundo = bpy.data.worlds.new("AD_World")
    mundo.use_nodes = True
    cena.world = mundo
    nodes, links = mundo.node_tree.nodes, mundo.node_tree.links
    nodes.clear()
    fundo = nodes.new("ShaderNodeBackground")
    fundo.inputs[0].default_value = (*bg_color, 1.0)
    fundo.inputs[1].default_value = bg_strength * 0.15
    saida_mundo = nodes.new("ShaderNodeOutputWorld")
    links.new(fundo.outputs["Background"], saida_mundo.inputs["Surface"])

    # 3-point lighting (Fatia 102), só quando o .blend não traz luz própria
    # — mesmo respeito da câmera automática ao trabalho do autor do asset.
    # Sun (direcional) em vez de Area: não precisa de posição nem de raciocinar
    # distância/escala do objeto, então funciona igual num vaso pequeno e
    # numa árvore de 4 metros sem reposicionar nada.
    if not any(o.type == "LIGHT" for o in visiveis):
        _nova_sun(cena, "AD_Key", DIRECAO_CAMERA, sun_energy)
        dir_fill = _girar_z(DIRECAO_CAMERA, 130)
        dir_fill.z *= 0.35  # mais rasante — sombra de preenchimento clássica
        _nova_sun(cena, "AD_Fill", dir_fill.normalized(), sun_energy * FRACAO_FILL)
        dir_rim = _girar_z(DIRECAO_CAMERA, 200)
        dir_rim.z = abs(dir_rim.z) + 0.6  # de trás e de cima — separa a silhueta
        _nova_sun(cena, "AD_Rim", dir_rim.normalized(), sun_energy * FRACAO_RIM)

    cena.render.engine = "CYCLES"  # pedido explícito do Rafael (antes: EEVEE)
    cena.cycles.samples = AMOSTRAS_CYCLES
    cena.cycles.use_denoising = True
    cena.render.resolution_x = cena.render.resolution_y = tamanho
    cena.render.resolution_percentage = 100
    cena.render.film_transparent = True
    cena.render.image_settings.file_format = "PNG"
    cena.render.image_settings.color_mode = "RGBA"
    cena.render.filepath = saida
    bpy.ops.render.render(write_still=True)
    print("ASSETDECK_RENDER_OK", saida, flush=True)


main()
