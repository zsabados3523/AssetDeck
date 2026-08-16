"""File Handlers: dão sentido ao que é ARRASTADO do AssetDeck para o Blender.

O Blender já sabe tratar .blend (Open/Append/Link) e .fbx/.obj sozinho — o
add-on não reimplementa isso. Ele acrescenta o que o Blender não faz:

- .hdr/.exr  → usar como iluminação do World
- imagem/mapa PBR → montar o material do set inteiro (não só abrir a imagem)

Quando há mais de um handler para a mesma extensão, o Blender mostra um menu
com as opções — a nossa aparece ao lado das nativas.
"""

from __future__ import annotations

import os

import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy.types import FileHandler, Operator, OperatorFileListElement

from . import materials, viewport

HDR_EXTS = ".hdr;.exr"
TEX_EXTS = ".png;.jpg;.jpeg;.tif;.tiff;.webp;.bmp;.tga"


def _primeiro_arquivo(op) -> str | None:
    """Caminho do primeiro arquivo solto (a API entrega diretório + lista)."""
    if getattr(op, "files", None):
        for f in op.files:
            if f.name:
                return os.path.join(op.directory, f.name)
    return op.filepath or None


class ASSETDECK_OT_drop_hdri(Operator):
    bl_idname = "assetdeck.drop_hdri"
    bl_label = "AssetDeck: usar como World (HDRI)"
    bl_description = "Ilumina a cena com este HDRI"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH", options={"SKIP_SAVE"})
    files: CollectionProperty(type=OperatorFileListElement, options={"SKIP_SAVE"})
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        return self.execute(context)

    def execute(self, context):
        caminho = _primeiro_arquivo(self)
        if not caminho or not os.path.isfile(caminho):
            self.report({"ERROR"}, "Arquivo de HDRI não encontrado.")
            return {"CANCELLED"}

        cena = context.scene
        mundo = cena.world
        if mundo is None:
            mundo = bpy.data.worlds.new("AD_World")
            cena.world = mundo
        mundo.use_nodes = True
        nodes, links = mundo.node_tree.nodes, mundo.node_tree.links
        nodes.clear()

        env = nodes.new("ShaderNodeTexEnvironment")
        env.location = (-300, 0)
        env.image = bpy.data.images.load(caminho, check_existing=True)
        fundo = nodes.new("ShaderNodeBackground")
        fundo.location = (0, 0)
        saida = nodes.new("ShaderNodeOutputWorld")
        saida.location = (250, 0)
        links.new(env.outputs["Color"], fundo.inputs["Color"])
        links.new(fundo.outputs["Background"], saida.inputs["Surface"])

        self.report({"INFO"}, f"World = {os.path.basename(caminho)}")
        return {"FINISHED"}


class ASSETDECK_OT_drop_texture(Operator):
    bl_idname = "assetdeck.drop_texture"
    bl_label = "AssetDeck: montar material PBR"
    bl_description = ("Pergunta ao AssetDeck quais mapas acompanham esta "
                      "textura e monta o material completo")
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype="DIR_PATH", options={"SKIP_SAVE"})
    files: CollectionProperty(type=OperatorFileListElement, options={"SKIP_SAVE"})
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})

    def invoke(self, context, event):
        self._alvo_sob_o_mouse = viewport.objeto_sob_o_mouse(context, event)
        return self.execute(context)

    def execute(self, context):
        from . import client

        caminho = _primeiro_arquivo(self)
        if not caminho:
            self.report({"ERROR"}, "Arquivo não encontrado.")
            return {"CANCELLED"}

        # Pergunta ao AssetDeck a que asset esse arquivo pertence
        try:
            resposta = client.request({"cmd": "asset_by_path", "path": caminho})
        except client.BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        mapas: dict[str, str] = {}
        for f in resposta.get("files", []):
            papel = f.get("map_role") or "none"
            if papel == "none":
                papel = "basecolor"
            mapas.setdefault(papel, f["path"])
        if not mapas:
            mapas = {"basecolor": caminho}

        nome = resposta.get("asset", {}).get("name") or os.path.basename(caminho)
        mat = materials.build_material(nome, mapas)

        # Soltou em cima de um objeto? Aplica NELE e o seleciona — é o
        # feedback visual de "onde o material foi parar" (Fatia 68). Sem
        # objeto sob o mouse (soltou no vazio), cai no comportamento
        # antigo: aplica em quem já estava selecionado.
        alvo = getattr(self, "_alvo_sob_o_mouse", None)
        if alvo is not None and hasattr(alvo.data, "materials"):
            alvos = [alvo]
            bpy.ops.object.select_all(action="DESELECT")
            alvo.select_set(True)
            context.view_layer.objects.active = alvo
        else:
            alvos = [o for o in context.selected_objects
                     if hasattr(o.data, "materials")]

        n = materials.apply_to_objects(mat, alvos) if alvos else 0
        self.report({"INFO"},
                    f"{mat.name}: {len(mapas)} mapa(s)" +
                    (f" em {n} objeto(s)" if n else " (nenhum objeto selecionado)"))
        return {"FINISHED"}


class ASSETDECK_FH_hdri(FileHandler):
    bl_idname = "ASSETDECK_FH_hdri"
    bl_label = "AssetDeck HDRI"
    bl_import_operator = "assetdeck.drop_hdri"
    bl_file_extensions = HDR_EXTS

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == "VIEW_3D"


class ASSETDECK_FH_texture(FileHandler):
    bl_idname = "ASSETDECK_FH_texture"
    bl_label = "AssetDeck Material PBR"
    bl_import_operator = "assetdeck.drop_texture"
    bl_file_extensions = TEX_EXTS

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == "VIEW_3D"


CLASSES = (
    ASSETDECK_OT_drop_hdri, ASSETDECK_OT_drop_texture,
    ASSETDECK_FH_hdri, ASSETDECK_FH_texture,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
