"""Roda DENTRO do Blender (blender -b -P) para exportar a geometria de um
.blend pra .obj — usado pelo visualizador 3D (Fase 6) pra "ler" um .blend
sem precisar de um parser do formato binário fechado do Blender.

Recebe, depois de '--':
  <arquivo.blend> <saida.obj>

Sem material/textura de propósito (`export_materials=False`) — o
visualizador ainda não lê MTL (mesmo escopo do parser de .obj caseiro).
"""

import sys

import bpy

caminho_blend = sys.argv[-2]
caminho_obj = sys.argv[-1]

bpy.ops.wm.open_mainfile(filepath=caminho_blend)
bpy.ops.wm.obj_export(filepath=caminho_obj, export_materials=False, export_uv=False)
