"""Monta o material PBR no Blender a partir dos mapas do AssetDeck.

Estratégia (escolha do Rafael): um NODE GROUP fechado com as texturas já
conectadas, e um material que usa esse grupo ligado ao Principled BSDF.
O shader editor fica limpo e o grupo pode ser reusado em outros materiais.
"""

from __future__ import annotations

import bpy

# Mapas que entram como cor (sRGB); todo o resto é dado técnico (Non-Color)
COLOR_ROLES = {"basecolor", "emission"}

# Ordem vertical dos nós de textura dentro do grupo
ROLE_ORDER = [
    "basecolor", "roughness", "glossiness", "metallic",
    "normal", "height", "ao", "opacity", "emission", "specular",
]

GROUP_PREFIX = "AD_"


def _socket(interface, nome: str, tipo: str, in_out: str):
    """Cria um socket no node group (API 4.x/5.x)."""
    return interface.new_socket(name=nome, in_out=in_out, socket_type=tipo)


def build_node_group(nome: str, mapas: dict[str, str]) -> bpy.types.NodeTree:
    """Cria um node group com as texturas do set.

    `mapas` = {map_role: caminho absoluto}. Retorna o NodeTree pronto.
    Uma nova aplicação não pode destruir o grupo usado por materiais antigos.
    """
    nome_grupo = f"{GROUP_PREFIX}{nome}"
    grupo = bpy.data.node_groups.new(nome_grupo, "ShaderNodeTree")
    iface = grupo.interface

    # Entradas: controle de escala do UV
    _socket(iface, "Scale", "NodeSocketFloat", "INPUT").default_value = 1.0

    entrada = grupo.nodes.new("NodeGroupInput")
    entrada.location = (-900, 0)
    saida = grupo.nodes.new("NodeGroupOutput")
    saida.location = (500, 0)

    # Mapeamento de UV compartilhado por todas as texturas
    uv = grupo.nodes.new("ShaderNodeTexCoord")
    uv.location = (-750, 300)
    mapping = grupo.nodes.new("ShaderNodeMapping")
    mapping.location = (-580, 300)
    grupo.links.new(uv.outputs["UV"], mapping.inputs["Vector"])
    combina = grupo.nodes.new("ShaderNodeCombineXYZ")
    combina.location = (-750, 120)
    for eixo in ("X", "Y", "Z"):
        grupo.links.new(entrada.outputs["Scale"], combina.inputs[eixo])
    grupo.links.new(combina.outputs["Vector"], mapping.inputs["Scale"])

    y = 400
    for papel in ROLE_ORDER:
        caminho = mapas.get(papel)
        if not caminho:
            continue
        tex = grupo.nodes.new("ShaderNodeTexImage")
        tex.location = (-350, y)
        tex.label = papel
        tex.image = bpy.data.images.load(caminho, check_existing=True)
        # Colorspace correto: normal/rough/metal/height como dado, não cor
        tex.image.colorspace_settings.name = (
            "sRGB" if papel in COLOR_ROLES else "Non-Color"
        )
        grupo.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        y -= 300

        if papel == "basecolor":
            _socket(iface, "Base Color", "NodeSocketColor", "OUTPUT")
            if "ao" in mapas:
                # AO multiplicado na cor base (o nó de AO é ligado no fim)
                mix = grupo.nodes.new("ShaderNodeMix")
                mix.name = "AD_AO_Mix"
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.location = (-100, y + 300)
                mix.inputs["Factor"].default_value = 1.0
                grupo.links.new(tex.outputs["Color"], mix.inputs[6])  # A
                grupo.links.new(mix.outputs[2], saida.inputs["Base Color"])
            else:
                grupo.links.new(tex.outputs["Color"], saida.inputs["Base Color"])

        elif papel == "roughness":
            _socket(iface, "Roughness", "NodeSocketFloat", "OUTPUT")
            grupo.links.new(tex.outputs["Color"], saida.inputs["Roughness"])

        elif papel == "glossiness" and "roughness" not in mapas:
            # Glossiness = o inverso de roughness
            _socket(iface, "Roughness", "NodeSocketFloat", "OUTPUT")
            inv = grupo.nodes.new("ShaderNodeInvert")
            inv.location = (-100, y + 300)
            grupo.links.new(tex.outputs["Color"], inv.inputs["Color"])
            grupo.links.new(inv.outputs["Color"], saida.inputs["Roughness"])

        elif papel == "metallic":
            _socket(iface, "Metallic", "NodeSocketFloat", "OUTPUT")
            grupo.links.new(tex.outputs["Color"], saida.inputs["Metallic"])

        elif papel == "normal":
            _socket(iface, "Normal", "NodeSocketVector", "OUTPUT")
            nmap = grupo.nodes.new("ShaderNodeNormalMap")
            nmap.location = (-100, y + 300)
            grupo.links.new(tex.outputs["Color"], nmap.inputs["Color"])
            grupo.links.new(nmap.outputs["Normal"], saida.inputs["Normal"])

        elif papel == "height":
            _socket(iface, "Height", "NodeSocketFloat", "OUTPUT")
            grupo.links.new(tex.outputs["Color"], saida.inputs["Height"])

        elif papel == "opacity":
            _socket(iface, "Alpha", "NodeSocketFloat", "OUTPUT")
            grupo.links.new(tex.outputs["Color"], saida.inputs["Alpha"])

        elif papel == "emission":
            _socket(iface, "Emission", "NodeSocketColor", "OUTPUT")
            grupo.links.new(tex.outputs["Color"], saida.inputs["Emission"])

    # Liga o AO no mix da base color (ambos os nós já existem a esta altura)
    mix = grupo.nodes.get("AD_AO_Mix")
    ao_tex = next((n for n in grupo.nodes
                   if n.type == "TEX_IMAGE" and n.label == "ao"), None)
    if mix is not None and ao_tex is not None:
        grupo.links.new(ao_tex.outputs["Color"], mix.inputs[7])  # B

    return grupo


def build_material(nome: str, mapas: dict[str, str]) -> bpy.types.Material:
    """Material completo: node group → Principled BSDF → Output."""
    grupo = build_node_group(nome, mapas)

    mat = bpy.data.materials.new(f"{GROUP_PREFIX}{nome}")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    node_grupo = nodes.new("ShaderNodeGroup")
    node_grupo.node_tree = grupo
    node_grupo.location = (-300, 0)
    node_grupo.width = 220

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (50, 0)
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # Liga cada saída existente do grupo ao slot correspondente do Principled
    destino = {
        "Base Color": "Base Color", "Roughness": "Roughness",
        "Metallic": "Metallic", "Normal": "Normal", "Alpha": "Alpha",
    }
    for saida_nome, entrada_nome in destino.items():
        if saida_nome in node_grupo.outputs and entrada_nome in bsdf.inputs:
            links.new(node_grupo.outputs[saida_nome], bsdf.inputs[entrada_nome])

    if "Emission" in node_grupo.outputs and "Emission Color" in bsdf.inputs:
        links.new(node_grupo.outputs["Emission"], bsdf.inputs["Emission Color"])

    # Deslocamento vai para o Output (real no Cycles, bump no EEVEE)
    if "Height" in node_grupo.outputs:
        disp = nodes.new("ShaderNodeDisplacement")
        disp.location = (50, -400)
        disp.inputs["Scale"].default_value = 0.05
        links.new(node_grupo.outputs["Height"], disp.inputs["Height"])
        links.new(disp.outputs["Displacement"], out.inputs["Displacement"])

    if "Alpha" in node_grupo.outputs and hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"

    return mat


def apply_to_objects(mat: bpy.types.Material, objetos,
                     substituir: bool = True) -> int:
    """Aplica o material aos objetos que aceitam material. Retorna quantos.

    substituir=False adiciona um slot novo em vez de trocar o material atual.
    """
    aplicados = 0
    for obj in objetos:
        if not hasattr(obj.data, "materials"):
            continue
        if substituir and obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        aplicados += 1
    return aplicados
