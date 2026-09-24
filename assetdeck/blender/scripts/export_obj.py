"""Roda DENTRO do Blender (blender -b -P) para exportar a geometria de um
.blend pra .obj — usado pelo visualizador 3D (Fase 6) pra "ler" um .blend
sem precisar de um parser do formato binário fechado do Blender.

Recebe, depois de '--':
  <arquivo.blend> <saida.obj>

Inclui UVs e materiais para o visualizador mostrar a textura de cor base.
"""

import sys

import bpy

caminho_blend = sys.argv[-2]
caminho_obj = sys.argv[-1]

bpy.ops.wm.open_mainfile(filepath=caminho_blend)
bpy.ops.wm.obj_export(filepath=caminho_obj, export_materials=True, export_uv=True,
                      path_mode='ABSOLUTE')
