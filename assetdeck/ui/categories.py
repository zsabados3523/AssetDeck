"""Categorias da barra de filtro (Fatia 31).

Agrupa os `asset_type` do schema em rótulos que fazem sentido pro Rafael —
`pbr_set`/`other` viram "Materiais", `ies`/`lut`/`psd`/`reference` viram
"Documentos". É mapa de UI: o banco continua guardando o asset_type cru.
"""

from __future__ import annotations

from typing import NamedTuple


class Category(NamedTuple):
    key: str
    label: str
    icon: str
    asset_types: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category("modelos", "Modelos", "cat-modelos", ("model", "scene")),
    Category("materiais", "Materiais", "cat-materiais", ("pbr_set", "other")),
    Category("imagens", "Imagens", "cat-imagens", ("texture", "cutout")),
    Category("hdris", "HDRIs", "cat-hdris", ("hdri",)),
    Category("vetores", "Vetores", "cat-vetores", ("vector",)),
    Category("documentos", "Documentos", "cat-documentos",
             ("reference", "psd", "ies", "lut")),
)

BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}

TYPE_LABELS: dict[str, str] = {
    "model": "Modelo 3D",
    "scene": "Cena 3D",
    "pbr_set": "Material PBR",
    "other": "Outro material",
    "texture": "Textura",
    "cutout": "Recorte",
    "hdri": "HDRI",
    "vector": "Vetor",
    "reference": "Referência",
    "psd": "Photoshop",
    "ies": "Perfil IES",
    "lut": "LUT",
}


def category_of(asset_type: str) -> Category | None:
    """Em qual categoria este asset_type cai (None se for tipo desconhecido)."""
    for c in CATEGORIES:
        if asset_type in c.asset_types:
            return c
    return None


def type_label_of(asset_type: str) -> str:
    """Rótulo de tela mais específico que a categoria de filtro."""
    return TYPE_LABELS.get(asset_type, asset_type)
