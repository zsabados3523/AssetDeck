"""AssetDeck Bridge — add-on que conversa com o AssetDeck pelo localhost.

Instalado automaticamente pelo AssetDeck (menu Blender → Instalar add-on).
Não acessa a internet: só 127.0.0.1, com token.
"""

bl_info = {
    "name": "AssetDeck Bridge",
    "author": "AssetDeck",
    "version": (0, 4, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > AssetDeck",
    "description": "Navegue a biblioteca do AssetDeck e aplique materiais PBR.",
    "category": "Import-Export",
}

import bpy  # noqa: E402
from bpy.props import (  # noqa: E402
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup  # noqa: E402

from . import client, drops, exporter, importer, materials, thumbs  # noqa: E402


# ---- dados na cena ----

class AssetDeckItem(PropertyGroup):
    asset_id: IntProperty()
    name: StringProperty()
    asset_type: StringProperty()
    primary_path: StringProperty()
    thumb_path: StringProperty()
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
    escala: FloatProperty(
        name="Escala UV", default=1.0, min=0.001, soft_max=20.0,
        description="Repetição da textura no objeto",
    )
    substituir: BoolProperty(
        name="Substituir material existente", default=True,
        description="Desmarque para adicionar um slot novo em vez de trocar",
    )


def _selecionado(context):
    estado = context.scene.assetdeck
    if 0 <= estado.indice < len(estado.itens):
        return estado.itens[estado.indice]
    return None


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

        thumbs.clear()
        estado.itens.clear()
        for a in resposta.get("assets", []):
            item = estado.itens.add()
            item.asset_id = a["id"]
            item.name = a["name"]
            item.asset_type = a["asset_type"]
            item.primary_path = a["primary_path"]
            item.thumb_path = a.get("thumb_path") or ""
            item.files_count = a["files_count"]
        estado.indice = 0
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


class ASSETDECK_OT_apply_material(Operator):
    bl_idname = "assetdeck.apply_material"
    bl_label = "Aplicar material"
    bl_description = ("Monta o node group PBR do asset selecionado e aplica "
                      "aos objetos selecionados")

    @classmethod
    def poll(cls, context):
        item = _selecionado(context)
        return item is not None and item.asset_type in {"pbr_set", "texture"}

    def execute(self, context):
        estado = context.scene.assetdeck
        item = _selecionado(context)
        if item is None:
            self.report({"ERROR"}, "Selecione um asset na lista.")
            return {"CANCELLED"}

        try:
            resposta = client.request({"cmd": "get_asset", "id": item.asset_id})
        except client.BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        mapas: dict[str, str] = {}
        for f in resposta.get("files", []):
            papel = f.get("map_role") or "none"
            if papel == "none":
                # Textura solta (não agrupada): entra como cor base
                papel = "basecolor"
            mapas.setdefault(papel, f["path"])
        if not mapas:
            self.report({"ERROR"}, "Este asset não tem mapas utilizáveis.")
            return {"CANCELLED"}

        try:
            mat = materials.build_material(item.name, mapas)
        except Exception as exc:
            self.report({"ERROR"}, f"Falha ao montar o material: {exc}")
            return {"CANCELLED"}

        # Escala de UV escolhida no painel
        for node in mat.node_tree.nodes:
            if node.type == "GROUP" and "Scale" in node.inputs:
                node.inputs["Scale"].default_value = estado.escala

        alvos = [o for o in context.selected_objects if hasattr(o.data, "materials")]
        if not alvos and context.active_object is not None:
            alvos = [context.active_object]
        if not alvos:
            self.report({"WARNING"},
                        f"Material '{mat.name}' criado, mas nenhum objeto "
                        "selecionado para aplicar.")
            return {"FINISHED"}

        n = materials.apply_to_objects(mat, alvos, substituir=estado.substituir)
        self.report({"INFO"},
                    f"{mat.name}: {len(mapas)} mapa(s) em {n} objeto(s)")
        return {"FINISHED"}


# ---- interface ----

class ASSETDECK_UL_assets(bpy.types.UIList):
    def draw_item(self, _ctx, layout, _data, item, _icon, _active, _prop):
        icones = {
            "pbr_set": "MATERIAL", "texture": "TEXTURE", "hdri": "WORLD",
            "model": "MESH_DATA", "cutout": "IMAGE_RGB_ALPHA",
        }
        icon_id = thumbs.icon_id(item.thumb_path)
        if icon_id:
            layout.label(text=item.name, icon_value=icon_id)
        else:
            layout.label(text=item.name, icon=icones.get(item.asset_type, "FILE"))
        if item.files_count > 1:
            layout.label(text=f"{item.files_count}")


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

        # Preview grande do item selecionado (pedido do Rafael)
        item = _selecionado(context)
        if item is not None:
            icon_id = thumbs.icon_id(item.thumb_path)
            caixa = layout.box()
            if icon_id:
                caixa.template_icon(icon_value=icon_id, scale=7.0)
            else:
                caixa.label(text="(sem miniatura pronta)", icon="IMAGE_DATA")
            caixa.label(text=item.name)
            caixa.label(text=f"{item.asset_type} · {item.files_count} arquivo(s)")

        layout.separator()
        layout.prop(estado, "escala")
        layout.prop(estado, "substituir")
        layout.operator("assetdeck.apply_material", icon="MATERIAL")

        layout.separator()
        layout.operator("assetdeck.save_to_library", icon="EXPORT")

        layout.separator()
        layout.label(text=estado.status, icon="INFO")
        layout.operator("assetdeck.ping", icon="PLUGIN")


CLASSES = (
    AssetDeckItem, AssetDeckState,
    ASSETDECK_OT_refresh, ASSETDECK_OT_ping, ASSETDECK_OT_apply_material,
    ASSETDECK_UL_assets, ASSETDECK_PT_panel,
)


def register():
    thumbs.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.assetdeck = bpy.props.PointerProperty(type=AssetDeckState)
    drops.register()     # HDRI / textura soltos na viewport
    importer.register()  # .blend solto → menu Append/Link (& Place)
    exporter.register()  # salvar seleção de volta na biblioteca


def unregister():
    exporter.unregister()
    importer.unregister()
    drops.unregister()
    del bpy.types.Scene.assetdeck
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    thumbs.unregister()
