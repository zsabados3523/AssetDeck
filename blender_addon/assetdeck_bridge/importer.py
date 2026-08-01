"""Append/Link de .blend com presets — inspirado no fluxo do Connecter.

Soltar um .blend vindo do AssetDeck abre um menu com o que importar
(Objects / Materials / Collections) e como (Append ou Link), além das
variantes "& Place", que deixam o que veio grudado no mouse para você
posicionar com um clique.
"""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import FileHandler, Menu, Operator

TIPOS = (
    ("objects", "Objects", "Objetos do arquivo"),
    ("materials", "Materials", "Materiais do arquivo"),
    ("collections", "Collections", "Coleções do arquivo"),
)


def _conteudo(filepath: str) -> dict[str, list[str]]:
    """O que existe dentro do .blend, sem importar nada."""
    achado = {"objects": [], "materials": [], "collections": []}
    with bpy.data.libraries.load(filepath, link=False) as (origem, _destino):
        for chave in achado:
            achado[chave] = list(getattr(origem, chave, []) or [])
    return achado


def _objeto_sob_o_mouse(context, event):
    """Objeto que está debaixo do cursor (para 'Append & Place' de material)."""
    if event is None or context.area is None or context.area.type != "VIEW_3D":
        return None
    try:
        from bpy_extras import view3d_utils

        region, rv3d = context.region, context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origem = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direcao = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        achou, _loc, _nor, _idx, obj, _m = context.scene.ray_cast(
            context.view_layer.depsgraph, origem, direcao
        )
        return obj if achou else None
    except Exception:
        return None


def _ponto_do_mouse(context, event):
    """Coordenada 3D sob o cursor (plano z=0), ou None fora da viewport."""
    if event is None or context.area is None or context.area.type != "VIEW_3D":
        return None
    try:
        from bpy_extras import view3d_utils

        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origem = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direcao = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        if abs(direcao.z) < 1e-6:
            return None
        t = -origem.z / direcao.z
        return origem + direcao * t if t > 0 else None
    except Exception:
        return None


class ASSETDECK_OT_import_blend(Operator):
    bl_idname = "assetdeck.import_blend"
    bl_label = "AssetDeck: importar do .blend"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
    datablock: EnumProperty(items=TIPOS, default="objects", options={"SKIP_SAVE"})
    link: BoolProperty(default=False, options={"SKIP_SAVE"})
    place: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        self._ponto = _ponto_do_mouse(context, event)
        self._sob_o_mouse = _objeto_sob_o_mouse(context, event)
        return self.execute(context)

    def execute(self, context):
        caminho = self.filepath or context.window_manager.assetdeck_drop_path
        if not caminho or not os.path.isfile(caminho):
            self.report({"ERROR"}, "Arquivo .blend não encontrado.")
            return {"CANCELLED"}

        try:
            with bpy.data.libraries.load(caminho, link=self.link) as (origem, destino):
                nomes = list(getattr(origem, self.datablock, []) or [])
                if not nomes:
                    self.report({"WARNING"},
                                f"Este .blend não tem {self.datablock}.")
                    return {"CANCELLED"}
                setattr(destino, self.datablock, nomes)
            # Fora do `with`, `destino` guarda os DATABLOCKS de verdade.
            # (Procurar por nome falha: o Blender renomeia para .001 quando
            #  já existe algo com o mesmo nome na cena.)
            self._carregados = [d for d in getattr(destino, self.datablock) if d]
        except Exception as exc:
            self.report({"ERROR"}, f"Falha ao ler o .blend: {exc}")
            return {"CANCELLED"}

        if not self._carregados:
            self.report({"WARNING"}, f"Nada foi carregado de {self.datablock}.")
            return {"CANCELLED"}

        verbo = "Link" if self.link else "Append"
        if self.datablock == "materials":
            return self._aplicar_materiais(context, verbo)
        return self._trazer_para_a_cena(context, verbo)

    # ---- destinos ----

    def _aplicar_materiais(self, context, verbo: str) -> set[str]:
        mats = self._carregados
        # No modo "& Place", o alvo é o objeto sob o cursor — é onde você
        # soltou. Sem ele (ou fora do modo), valem os selecionados.
        sob = getattr(self, "_sob_o_mouse", None) if self.place else None
        if sob is not None and hasattr(sob.data, "materials"):
            alvos = [sob]
        else:
            alvos = [o for o in context.selected_objects
                     if hasattr(o.data, "materials")]
        if not alvos:
            self.report({"INFO"},
                        f"{verbo}: {len(mats)} material(is) carregado(s). "
                        "Selecione um objeto (ou solte sobre ele) para aplicar.")
            return {"FINISHED"}
        for obj in alvos:
            if obj.data.materials:
                obj.data.materials[0] = mats[0]
            else:
                obj.data.materials.append(mats[0])
        onde = f"'{alvos[0].name}'" if len(alvos) == 1 else f"{len(alvos)} objetos"
        self.report({"INFO"}, f"{verbo}: '{mats[0].name}' em {onde}")
        return {"FINISHED"}

    def _trazer_para_a_cena(self, context, verbo: str) -> set[str]:
        colecao = context.collection
        novos = []
        if self.datablock == "objects":
            for obj in self._carregados:
                if obj.name not in colecao.objects:
                    colecao.objects.link(obj)
                    novos.append(obj)
        else:  # collections → instância na cena (não duplica a geometria)
            for col in self._carregados:
                inst = bpy.data.objects.new(col.name, None)
                inst.instance_type = "COLLECTION"
                inst.instance_collection = col
                colecao.objects.link(inst)
                novos.append(inst)

        if not novos:
            self.report({"WARNING"}, "Nada novo para trazer (já estava na cena?).")
            return {"CANCELLED"}

        ponto = getattr(self, "_ponto", None)
        bpy.ops.object.select_all(action="DESELECT")
        for obj in novos:
            if ponto is not None and obj.parent is None:
                obj.location = ponto
            obj.select_set(True)
        context.view_layer.objects.active = novos[0]

        self.report({"INFO"}, f"{verbo}: {len(novos)} {self.datablock}")

        if self.place and context.area and context.area.type == "VIEW_3D":
            # Deixa o que veio grudado no mouse, como o "& Place" do Connecter
            return bpy.ops.transform.translate("INVOKE_DEFAULT")
        return {"FINISHED"}


ICONES = {
    "objects": "OBJECT_DATA",
    "materials": "MATERIAL",
    "collections": "OUTLINER_COLLECTION",
}


class _SubmenuBase(Menu):
    """Submenu com Objects / Materials / Collections para um modo."""

    link = False
    place = False

    def draw(self, context):
        caminho = context.window_manager.assetdeck_drop_path
        for tipo, rotulo, _desc in TIPOS:
            op = self.layout.operator(
                "assetdeck.import_blend", text=rotulo, icon=ICONES[tipo]
            )
            op.filepath = caminho
            op.datablock = tipo
            op.link = self.link
            op.place = self.place


class ASSETDECK_MT_link_place(_SubmenuBase):
    bl_idname = "ASSETDECK_MT_link_place"
    bl_label = "Link & Place"
    link, place = True, True


class ASSETDECK_MT_append_place(_SubmenuBase):
    bl_idname = "ASSETDECK_MT_append_place"
    bl_label = "Append & Place"
    link, place = False, True


class ASSETDECK_MT_link(_SubmenuBase):
    bl_idname = "ASSETDECK_MT_link"
    bl_label = "Link"
    link, place = True, False


class ASSETDECK_MT_append(_SubmenuBase):
    bl_idname = "ASSETDECK_MT_append"
    bl_label = "Append"
    link, place = False, False


class ASSETDECK_MT_drop_blend(Menu):
    bl_idname = "ASSETDECK_MT_drop_blend"
    bl_label = "AssetDeck"

    def draw(self, context):
        caminho = context.window_manager.assetdeck_drop_path
        layout = self.layout
        layout.label(text=os.path.basename(caminho), icon="BLENDER")
        layout.separator()
        # Cada entrada abre um submenu com Objects / Materials / Collections
        layout.menu(ASSETDECK_MT_link_place.bl_idname, icon="LINKED")
        layout.menu(ASSETDECK_MT_append_place.bl_idname, icon="APPEND_BLEND")
        layout.separator()
        layout.menu(ASSETDECK_MT_link.bl_idname, icon="LINKED")
        layout.menu(ASSETDECK_MT_append.bl_idname, icon="APPEND_BLEND")
        layout.separator()
        op = layout.operator("wm.open_mainfile", text="Open", icon="FILE_FOLDER")
        op.filepath = caminho


class ASSETDECK_OT_drop_blend(Operator):
    """Ponto de entrada do arrasto: guarda o arquivo e abre o menu."""

    bl_idname = "assetdeck.drop_blend"
    bl_label = "AssetDeck: Append / Link…"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
    directory: StringProperty(subtype="DIR_PATH", options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        caminho = self.filepath
        if not caminho and self.directory:
            caminho = self.directory
        if not caminho or not os.path.isfile(caminho):
            self.report({"ERROR"}, "Arquivo .blend não encontrado.")
            return {"CANCELLED"}
        context.window_manager.assetdeck_drop_path = caminho
        bpy.ops.wm.call_menu(name=ASSETDECK_MT_drop_blend.bl_idname)
        return {"FINISHED"}

    def execute(self, context):
        return self.invoke(context, None)


class ASSETDECK_FH_blend(FileHandler):
    bl_idname = "ASSETDECK_FH_blend"
    bl_label = "AssetDeck (Append/Link)"
    bl_import_operator = "assetdeck.drop_blend"
    bl_file_extensions = ".blend"

    @classmethod
    def poll_drop(cls, context):
        return context.area and context.area.type == "VIEW_3D"


CLASSES = (
    ASSETDECK_OT_import_blend,
    ASSETDECK_MT_link_place, ASSETDECK_MT_append_place,
    ASSETDECK_MT_link, ASSETDECK_MT_append,
    ASSETDECK_MT_drop_blend,
    ASSETDECK_OT_drop_blend, ASSETDECK_FH_blend,
)


def register() -> None:
    bpy.types.WindowManager.assetdeck_drop_path = StringProperty(default="")
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.assetdeck_drop_path
