"""Agrupamento de sets PBR: N mapas irmãos viram 1 asset.

Heurística calibrada nos padrões reais da testlib:
- Poliigon:  Nome_8607_Displacement.tiff · Nome_COL_4K.jpg
- ambientCG: Nome_2K_Color.jpg · Nome_2K-JPG_NormalGL.jpg
- CC0/cgbookcase: Nome_ROUGHNESS_1K_METALNESS.png · Nome_DISP16_4K.tiff
- Maxtree/Evermotion: Nome_Base_Color.png · Nome_Normal.png

Regras de segurança:
- Só agrupa arquivos com papel (map_role) reconhecido no nome.
- Exige ≥2 papéis distintos e pelo menos um papel-âncora
  (basecolor/normal/roughness) — nada de juntar arquivos ao acaso.
- Respeita group_locked: correção manual do Rafael vale para sempre.
- Nada é apagado: assets fundidos ganham deleted_at (soft delete).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# token normalizado → map_role do schema
ROLE_ALIASES = {
    # cor base
    "basecolor": "basecolor", "basecolour": "basecolor", "albedo": "basecolor",
    "diffuse": "basecolor", "diff": "basecolor", "col": "basecolor",
    "color": "basecolor", "colour": "basecolor",
    # rugosidade / brilho
    "roughness": "roughness", "rough": "roughness", "rgh": "roughness",
    "glossiness": "glossiness", "gloss": "glossiness",
    # normal
    "normal": "normal", "nrm": "normal", "nor": "normal", "norm": "normal",
    "normalgl": "normal", "normaldx": "normal",
    # altura / deslocamento
    "height": "height", "disp": "height", "displacement": "height",
    "disp16": "height", "bump": "height",
    # oclusão
    "ao": "ao", "ambientocclusion": "ao", "occlusion": "ao",
    # metal
    "metallic": "metallic", "metalness": "metallic", "metal": "metallic",
    # especular
    "specular": "specular", "spec": "specular",
    # transparência
    "opacity": "opacity", "alpha": "opacity", "mask": "opacity",
    # emissão
    "emission": "emission", "emissive": "emission",
}

# Papéis que sozinhos justificam um set (evita falsos positivos)
ANCHOR_ROLES = {"basecolor", "normal", "roughness"}

# Ordem de preferência para eleger o arquivo principal (capa)
PRIMARY_ORDER = ["basecolor", "normal", "roughness", "height", "ao",
                 "metallic", "specular", "opacity", "emission"]

# Tokens de resolução/formato que não fazem parte do nome-base
_NOISE_RE = re.compile(r"^(\d+k|\d+px|8bit|16bit|32bit|jpg|jpeg|png|tif{1,2}|exr|var\d+)$")

_TOKEN_SPLIT = re.compile(r"[ _\-.]+")


@dataclass
class GroupStats:
    sets_created: int = 0
    files_grouped: int = 0
    assets_merged: int = 0


def parse_stem(stem: str) -> tuple[str, str | None]:
    """Nome do arquivo (sem extensão) → (chave-base, papel ou None).

    'MetalWire_ROUGHNESS_1K_METALNESS' → ('metalwire', 'roughness')
    'Green_leaf_10_2K_front_Base_Color' → ('green leaf 10 2k front', 'basecolor')
    'foto_ferias' → ('foto ferias', None)
    """
    tokens = [t.lower() for t in _TOKEN_SPLIT.split(stem) if t]

    # Papéis de dois tokens ('Base_Color') são vistos como token colado
    role = None
    role_start = None
    for i in range(len(tokens)):
        for j in (2, 1):  # tenta o par colado primeiro
            joined = "".join(tokens[i:i + j])
            if joined in ROLE_ALIASES:
                role = ROLE_ALIASES[joined]
                role_start = i
                break
        if role:
            break

    if role is None:
        return " ".join(tokens), None

    base = [t for t in tokens[:role_start] if not _NOISE_RE.match(t)]
    return " ".join(base), role


def apply_grouping(conn: sqlite3.Connection, library_id: int) -> GroupStats:
    """Uma passada de agrupamento sobre os assets 1:1 ainda não travados."""
    stats = GroupStats()
    now = datetime.now(timezone.utc).isoformat()

    # Candidatos: assets ativos de imagem, com UM arquivo, sem trava manual
    rows = conn.execute(
        """SELECT a.id AS asset_id, a.name, a.notes, f.id AS file_id, f.rel_path
           FROM assets a JOIN files f ON f.asset_id = a.id
           WHERE a.library_id = ? AND a.deleted_at IS NULL
             AND a.group_locked = 0 AND a.asset_type = 'texture'
             AND f.deleted_at IS NULL
             AND (SELECT COUNT(*) FROM files f2
                  WHERE f2.asset_id = a.id AND f2.deleted_at IS NULL) = 1""",
        (library_id,),
    ).fetchall()

    # (pasta, chave-base) → lista de (papel, row)
    grupos: dict[tuple[str, str], list[tuple[str, sqlite3.Row]]] = {}
    for row in rows:
        rel = row["rel_path"]
        directory = rel.rsplit("/", 1)[0] if "/" in rel else ""
        stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        base, role = parse_stem(stem)
        if role is None or not base:
            continue
        grupos.setdefault((directory, base), []).append((role, row))

    for (directory, base), membros in grupos.items():
        papeis = {r for r, _ in membros}
        if len(membros) < 2 or len(papeis) < 2 or not (papeis & ANCHOR_ROLES):
            continue

        # Mantém o asset do arquivo principal; funde os demais nele
        membros.sort(key=lambda m: PRIMARY_ORDER.index(m[0])
                     if m[0] in PRIMARY_ORDER else 99)
        principal_role, principal = membros[0]
        keeper_id = principal["asset_id"]

        nome_set = base.title() if base == base.lower() else base
        notas_fundidas = [m["notes"] for _r, m in membros if m["notes"]]
        conn.execute(
            """UPDATE assets SET name = ?, asset_type = 'pbr_set',
                                 notes = COALESCE(?, notes), updated_at = ?
               WHERE id = ?""",
            (nome_set, "\n".join(notas_fundidas) if notas_fundidas else None,
             now, keeper_id),
        )
        for role, m in membros:
            conn.execute(
                "UPDATE files SET asset_id = ?, map_role = ?, is_primary = ?, "
                "updated_at = ? WHERE id = ?",
                (keeper_id, role, 1 if m["file_id"] == principal["file_id"] else 0,
                 now, m["file_id"]),
            )
            if m["asset_id"] != keeper_id:
                conn.execute(
                    "UPDATE assets SET deleted_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, m["asset_id"]),
                )
                stats.assets_merged += 1
        stats.sets_created += 1
        stats.files_grouped += len(membros)
        log.info("Set PBR agrupado: %r (%s) — %d mapas: %s",
                 nome_set, directory or "(raiz)", len(membros),
                 ", ".join(sorted(r for r, _ in membros)))

    conn.commit()
    if stats.sets_created:
        from assetdeck.db.repos.assets import rebuild_fts

        rebuild_fts(conn)
    log.info("Agrupamento: %d sets criados, %d arquivos agrupados.",
             stats.sets_created, stats.files_grouped)
    return stats
