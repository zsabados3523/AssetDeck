"""Append/Link de .blend com presets — inspirado no fluxo do Connecter.

Soltar um .blend vindo do AssetDeck importa DIRETO, sem menu, sem
perguntar nada (Fatia 68): olha o conteúdo do arquivo e escolhe sozinho
Objects/Materials/Collections (o que existir), sempre em modo **Link**
(não Append — biblioteca grande, escolha do Rafael: o .blend final não
pode inchar copiando tudo pra dentro) e "& Place", que deixa o que veio
grudado no mouse para você posicionar com um clique. Segurar Shift ao
soltar abre o menu antigo (Append/Link × Objects/Materials/Collections)
pra quem quiser escolher na mão.
"""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import FileHandler, Menu, Operator

from . import viewport

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


class ASSETDECK_OT_import_blend(Operator):
    bl_idname = "assetdeck.import_blend"
    bl_label = "AssetDeck: importar do .blend"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE"})
    datablock: EnumProperty(items=TIPOS, default="objects", options={"SKIP_SAVE"})
    link: BoolProperty(default=False, options={"SKIP_SAVE"})
    place: BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        self._ponto = viewport.ponto_do_mouse(context, event)
        self._sob_o_mouse = viewport.objeto_sob_o_mouse(context, event)
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

    def invoke(self, context, event):
        caminho = self.filepath
        if not caminho and self.directory:
            caminho = self.directory
        if not caminho or not os.path.isfile(caminho):
            self.report({"ERROR"}, "Arquivo .blend não encontrado.")
            return {"CANCELLED"}
        context.window_manager.assetdeck_drop_path = caminho

        if event is not None and event.shift:
            bpy.ops.wm.call_menu(name=ASSETDECK_MT_drop_blend.bl_idname)
            return {"FINISHED"}

        # Padrão (Fatia 68): pula o menu, escolhendo sozinho o que dá pra
        # importar — Object/Material/Collection não é exigência do
        # Blender, é o próprio add-on que decide. Alguns .blend do
        # Rafael são packs de MATERIAL puro (só node group, sem malha
        # nenhuma) — nesses, "objects" sempre dava vazio e cancelava em
        # silêncio (o bug real por trás do "nada acontece" ao soltar um
        # material). Olhar o conteúdo primeiro custa pouco (só lista os
        # nomes, não carrega dado nenhum) e evita isso.
        try:
            conteudo = _conteudo(caminho)
        except Exception as exc:
            self.report({"ERROR"}, f"Falha ao ler o .blend: {exc}")
            return {"CANCELLED"}

        if conteudo["objects"]:
            datablock = "objects"
        elif conteudo["materials"]:
            datablock = "materials"
        elif conteudo["collections"]:
            datablock = "collections"
        else:
            self.report({"WARNING"},
                        "Este .blend não tem objetos, materiais nem "
                        "coleções pra importar.")
            return {"CANCELLED"}

        # Objects/Collections vêm grudados no mouse (Link & Place); um
        # material puro aplica direto no objeto sob o mouse (mesma mira
        # de _aplicar_materiais/drop_texture) — os dois são o feedback
        # visual de "onde vai parar", sem precisar escolher no menu.
        # Link (não Append) por escolha do Rafael: biblioteca grande,
        # arquivo .blend final não pode inchar copiando tudo pra dentro.
        return bpy.ops.assetdeck.import_blend(
            "INVOKE_DEFAULT", filepath=caminho, datablock=datablock,
            link=True, place=True,
        )

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
