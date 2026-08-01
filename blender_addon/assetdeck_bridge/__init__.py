"""AssetDeck Bridge — add-on que conversa com o AssetDeck pelo localhost.

Instalado automaticamente pelo AssetDeck (menu Blender → Instalar add-on).
Não acessa a internet: só 127.0.0.1, com token.
"""

bl_info = {
    "name": "AssetDeck Bridge",
    "author": "AssetDeck",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > AssetDeck",
    "description": "Navegue a biblioteca do AssetDeck dentro do Blender.",
    "category": "Import-Export",
}

import bpy  # noqa: E402
from bpy.props import (  # noqa: E402
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup  # noqa: E402

from . import client  # noqa: E402


# ---- dados na cena ----

class AssetDeckItem(PropertyGroup):
    asset_id: IntProperty()
    name: StringProperty()
    asset_type: StringProperty()
    primary_path: StringProperty()
    files_count: IntProperty()


class AssetDeckState(PropertyGroup):
    search: StringProperty(
        name="Buscar", description="Filtra por nome (igual à busca do AssetDeck)",
    )
    tipo: EnumProperty(
        name="Tipo",
        items=[
            ("ALL", "Todos", "Todos os tipos"),
            ("pbr_set", "Sets PBR", "Materiais PBR agrupados"),
            ("texture", "Texturas", "Texturas soltas"),
            ("hdri", "HDRIs", "Mapas de ambiente"),
            ("model", "Modelos", "Modelos 3D"),
        ],
        default="ALL",
    )
    itens: CollectionProperty(type=AssetDeckItem)
    indice: IntProperty(default=0)
    status: StringProperty(default="Ainda não conectado")


# ---- operadores ----

class ASSETDECK_OT_refresh(Operator):
    bl_idname = "assetdeck.refresh"
    bl_label = "Conectar / Atualizar"
    bl_description = "Busca os assets no AssetDeck (o app precisa estar aberto)"

    def execute(self, context):
        estado = context.scene.assetdeck
        tipos = None if estado.tipo == "ALL" else [estado.tipo]
        try:
            resposta = client.request(
                {"cmd": "list_assets", "search": estado.search, "types": tipos}
            )
        except client.BridgeError as exc:
            estado.itens.clear()
            estado.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        estado.itens.clear()
        for a in resposta.get("assets", []):
            item = estado.itens.add()
            item.asset_id = a["id"]
            item.name = a["name"]
            item.asset_type = a["asset_type"]
            item.primary_path = a["primary_path"]
            item.files_count = a["files_count"]
        estado.status = (
            f"{resposta.get('returned', 0)} de {resposta.get('total', 0)} assets"
        )
        return {"FINISHED"}


class ASSETDECK_OT_ping(Operator):
    bl_idname = "assetdeck.ping"
    bl_label = "Testar conexão"
    bl_description = "Verifica se o AssetDeck está aberto e respondendo"

    def execute(self, context):
        estado = context.scene.assetdeck
        try:
            resposta = client.request({"cmd": "ping"})
        except client.BridgeError as exc:
            estado.status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        estado.status = f"AssetDeck {resposta.get('version')} respondeu ✓"
        self.report({"INFO"}, estado.status)
        return {"FINISHED"}


# ---- interface ----

class ASSETDECK_UL_assets(bpy.types.UIList):
    def draw_item(self, _ctx, layout, _data, item, _icon, _active, _prop):
        icones = {
            "pbr_set": "MATERIAL", "texture": "TEXTURE", "hdri": "WORLD",
            "model": "MESH_DATA", "cutout": "IMAGE_RGB_ALPHA",
        }
        layout.label(text=item.name, icon=icones.get(item.asset_type, "FILE"))
        if item.files_count > 1:
            layout.label(text=f"{item.files_count} arq.")


class ASSETDECK_PT_panel(Panel):
    bl_label = "AssetDeck"
    bl_idname = "ASSETDECK_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AssetDeck"

    def draw(self, context):
        estado = context.scene.assetdeck
        layout = self.layout

        linha = layout.row(align=True)
        linha.prop(estado, "search", text="", icon="VIEWZOOM")
        linha.operator("assetdeck.refresh", text="", icon="FILE_REFRESH")
        layout.prop(estado, "tipo", text="")

        layout.template_list(
            "ASSETDECK_UL_assets", "", estado, "itens", estado, "indice", rows=8
        )
        layout.label(text=estado.status, icon="INFO")
        layout.operator("assetdeck.ping", icon="PLUGIN")


CLASSES = (
    AssetDeckItem, AssetDeckState,
    ASSETDECK_OT_refresh, ASSETDECK_OT_ping,
    ASSETDECK_UL_assets, ASSETDECK_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.assetdeck = bpy.props.PointerProperty(type=AssetDeckState)


def unregister():
    del bpy.types.Scene.assetdeck
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
