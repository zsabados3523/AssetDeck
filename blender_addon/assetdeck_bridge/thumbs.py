"""Miniaturas dentro do Blender (pedido do Rafael).

O AssetDeck já gera as thumbnails em ~/.cache/assetdeck/thumbs e manda o
caminho pela ponte; aqui elas viram ícones do Blender. Como o Flatpak tem
`filesystems=host`, o Blender lê esses arquivos sem cópia nenhuma.
"""

from __future__ import annotations

import os

import bpy.utils.previews

_colecao = None          # bpy.utils.previews collection
_por_caminho: dict[str, int] = {}   # caminho → icon_id


def register() -> None:
    global _colecao
    if _colecao is None:
        _colecao = bpy.utils.previews.new()


def unregister() -> None:
    global _colecao
    if _colecao is not None:
        bpy.utils.previews.remove(_colecao)
        _colecao = None
    _por_caminho.clear()


def icon_id(caminho: str) -> int:
    """icon_id da miniatura (0 = sem ícone; o chamador usa o ícone de tipo).

    Uma imagem ilegível nunca derruba o painel: vira 0 e segue.
    """
    if not caminho or _colecao is None:
        return 0
    if caminho in _por_caminho:
        return _por_caminho[caminho]
    if not os.path.isfile(caminho):
        _por_caminho[caminho] = 0
        return 0

    chave = f"ad_{abs(hash(caminho))}"
    try:
        item = _colecao.get(chave) or _colecao.load(chave, caminho, "IMAGE")
        _por_caminho[caminho] = item.icon_id
    except Exception:  # imagem corrompida, formato exótico…
        _por_caminho[caminho] = 0
    return _por_caminho[caminho]


def clear() -> None:
    """Esquece as miniaturas carregadas (usado ao atualizar a lista)."""
    _por_caminho.clear()
