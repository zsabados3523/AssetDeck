"""Onde está o mouse na cena 3D e o que tem embaixo dele.

Compartilhado por drops.py (textura → objeto sob o mouse) e importer.py
(.blend → ponto/objeto sob o mouse pro "Append & Place").
"""

from __future__ import annotations


def objeto_sob_o_mouse(context, event):
    """Objeto sob o cursor do mouse na viewport 3D (raycast), ou None."""
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


def ponto_do_mouse(context, event):
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
