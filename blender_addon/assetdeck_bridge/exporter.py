"""Salvar a seleção da cena de volta para a biblioteca do AssetDeck.

Cria um .blend NOVO com os objetos selecionados. Nunca sobrescreve nada
sem confirmação e nunca toca nos arquivos que já existem — a biblioteca
continua somente-leitura para tudo o que não é este arquivo novo.
"""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from . import client


class ASSETDECK_OT_save_to_library(Operator):
    bl_idname = "assetdeck.save_to_library"
    bl_label = "Salvar seleção na biblioteca"
    bl_description = ("Cria um .blend novo na biblioteca do AssetDeck com os "
                      "objetos selecionados")
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    filename: StringProperty()
    directory: StringProperty(subtype="DIR_PATH")
    filter_glob: StringProperty(default="*.blend", options={"HIDDEN"})
    sobrescrever: BoolProperty(
        name="Sobrescrever se já existir", default=False,
        description="Deixe desmarcado para nunca substituir um arquivo seu",
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, _event):
        # Abre o navegador já na raiz da biblioteca
        try:
            info = client.request({"cmd": "ping"})
            raiz = info.get("library_root") or os.path.expanduser("~")
        except client.BridgeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        ativo = context.active_object
        sugestao = (ativo.name if ativo else "asset").replace(" ", "_")
        self.directory = raiz + os.sep
        self.filename = f"{sugestao}.blend"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        selecionados = list(context.selected_objects)
        if not selecionados:
            self.report({"ERROR"}, "Nada selecionado para salvar.")
            return {"CANCELLED"}

        caminho = self.filepath
        if not caminho:
            caminho = os.path.join(self.directory, self.filename)
        if not caminho.lower().endswith(".blend"):
            caminho += ".blend"

        if os.path.exists(caminho) and not self.sobrescrever:
            self.report({"ERROR"},
                        f"Já existe '{os.path.basename(caminho)}'. Escolha outro "
                        "nome ou marque 'Sobrescrever'.")
            return {"CANCELLED"}

        # Leva junto os dados de que os objetos dependem (malhas, materiais…)
        conjunto = set(selecionados)
        for obj in selecionados:
            if obj.data is not None:
                conjunto.add(obj.data)
            for slot in getattr(obj, "material_slots", []):
                if slot.material is not None:
                    conjunto.add(slot.material)

        try:
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            bpy.data.libraries.write(caminho, conjunto, fake_user=True,
                                     compress=True)
        except Exception as exc:
            self.report({"ERROR"}, f"Não consegui salvar: {exc}")
            return {"CANCELLED"}

        # Avisa o AssetDeck para indexar o arquivo novo
        aviso = ""
        try:
            client.request({"cmd": "rescan"})
        except client.BridgeError as exc:
            aviso = f" (reindexe no AssetDeck: {exc})"

        self.report({"INFO"},
                    f"Salvo: {os.path.basename(caminho)} "
                    f"({len(selecionados)} objeto(s)){aviso}")
        return {"FINISHED"}


CLASSES = (ASSETDECK_OT_save_to_library,)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
