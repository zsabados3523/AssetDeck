"""Detecta texturas que são DEPENDÊNCIAS de um modelo/material irmão.

O fluxo do Rafael: cada material (Poliigon, PolyHaven…) é convertido num
.blend que fica ao lado dos mapas; modelos trazem suas texturas numa
subpasta. Nos dois casos ele quer ver o .blend — não os mapas soltos.

Regra: uma textura é dependência se existe um arquivo de modelo (.blend,
.fbx, .obj…) na mesma pasta ou em até DOIS níveis acima. Dois níveis cobrem
'Material/4K/mapa.jpg' e 'Modelo/textures/mapa.png' sem varrer a biblioteca
inteira para cima.

Também associa o preview que vem nos packs ('*_Preview1.png') como capa do
modelo irmão — o Poliigon já entrega essa imagem pronta.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Tipos que PODEM ser dependência (um modelo nunca é dependência de outro)
DEPENDENT_TYPES = ("texture", "pbr_set", "cutout")
# Tipos cuja presença numa pasta torna as texturas vizinhas dependências
OWNER_TYPES = ("model", "scene")

MAX_LEVELS_UP = 2

_PREVIEW_RE = re.compile(r"_preview\d*$", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir_of(rel_path: str) -> str:
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def _ancestors(directory: str, levels: int) -> list[str]:
    """['a/b/c', 'a/b', 'a'] limitado a `levels` subidas."""
    saida = [directory]
    atual = directory
    for _ in range(levels):
        if not atual:
            break
        atual = atual.rsplit("/", 1)[0] if "/" in atual else ""
        saida.append(atual)
    return saida


def detect(conn: sqlite3.Connection, library_id: int) -> int:
    """Recalcula is_dependency para a biblioteca. Retorna quantas mudaram.

    Uma pasta "tem modelo" se existe um .blend/.fbx nela OU em qualquer
    subpasta — packs como o Maxtree separam os .blend e os mapas em pastas
    IRMÃS (Vol_148/Blender_CyclesEevee/ e Vol_148/Maps/), e as texturas
    continuam sendo dependências daqueles modelos.
    """
    pastas_com_modelo: set[str] = set()
    for row in conn.execute(
        f"""SELECT DISTINCT f.rel_path FROM files f JOIN assets a ON a.id = f.asset_id
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})""",
        (library_id, *OWNER_TYPES),
    ):
        # A pasta do modelo e TODAS as suas ancestrais passam a "ter modelo"
        atual = _dir_of(row["rel_path"])
        while atual:
            pastas_com_modelo.add(atual)
            atual = atual.rsplit("/", 1)[0] if "/" in atual else ""
    # A raiz da biblioteca nunca conta: senão a biblioteca inteira viraria
    # dependência do primeiro modelo encontrado.
    pastas_com_modelo.discard("")

    candidatos = conn.execute(
        f"""SELECT a.id, a.is_dependency, f.rel_path
            FROM assets a JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(DEPENDENT_TYPES))})""",
        (library_id, *DEPENDENT_TYPES),
    ).fetchall()

    mudou = 0
    for row in candidatos:
        pasta = _dir_of(row["rel_path"])
        dependente = any(
            anc and anc in pastas_com_modelo
            for anc in _ancestors(pasta, MAX_LEVELS_UP)
        )
        novo = 1 if dependente else 0
        if novo != row["is_dependency"]:
            conn.execute(
                "UPDATE assets SET is_dependency = ?, updated_at = ? WHERE id = ?",
                (novo, _now(), row["id"]),
            )
            mudou += 1

    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE library_id = ? AND is_dependency = 1"
        " AND deleted_at IS NULL", (library_id,),
    ).fetchone()["n"]
    log.info("Dependências: %d assets marcados (%d mudaram nesta passada).",
             total, mudou)
    return mudou


def attach_pack_previews(conn: sqlite3.Connection, library_id: int,
                         library_root, previews_dir) -> int:
    """Usa os '*_Preview1.png' dos packs como capa do modelo irmão.

    Poliigon e outros já entregam essa imagem pronta — melhor do que
    renderizar. Retorna quantas capas foram criadas.
    """
    from pathlib import Path

    from assetdeck.db.repos import previews as previews_repo

    # Modelos sem capa, indexados por pasta
    modelos: dict[str, tuple[int, str]] = {}
    for row in conn.execute(
        f"""SELECT a.id, f.rel_path FROM assets a
            JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})
              AND NOT EXISTS (SELECT 1 FROM previews p
                              WHERE p.asset_id = a.id AND p.is_cover = 1
                                AND p.deleted_at IS NULL)""",
        (library_id, *OWNER_TYPES),
    ):
        modelos[_dir_of(row["rel_path"])] = (row["id"], row["rel_path"])

    if not modelos:
        return 0

    criadas = 0
    for row in conn.execute(
        """SELECT f.rel_path FROM files f JOIN assets a ON a.id = f.asset_id
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
        (library_id,),
    ):
        rel = row["rel_path"]
        nome = rel.rsplit("/", 1)[-1]
        base, _, ext = nome.rpartition(".")
        if ext.lower() not in ("png", "jpg", "jpeg") or not _PREVIEW_RE.search(base):
            continue
        alvo = modelos.get(_dir_of(rel))
        if alvo is None:
            continue
        asset_id, _p = alvo
        try:
            previews_repo.add(conn, asset_id, Path(library_root) / rel,
                              Path(previews_dir), origin="auto")
            criadas += 1
            del modelos[_dir_of(rel)]  # um preview por modelo basta
        except (OSError, FileNotFoundError):
            log.warning("Preview do pack ilegível: %s", rel, exc_info=True)

    if criadas:
        log.info("Capas automáticas de packs: %d modelos ganharam preview.", criadas)
    return criadas


def attach_stem_match_previews(conn: sqlite3.Connection, library_id: int,
                               library_root, previews_dir,
                               hide_source: bool = False) -> int:
    """Casa 'Cadeira.blend' com 'Cadeira.jpg' pelo NOME (mesma pasta, mesmo
    nome-base) e usa a imagem como capa automática do modelo (Fatia 57,
    pedido do Rafael).

    Diferente de `attach_pack_previews` (que casa por PASTA, um preview por
    pasta): aqui uma pasta pode ter vários modelos, cada um casando com a
    própria imagem de mesmo nome. Só aplica quando há exatamente UM
    candidato por modelo — 2+ imagens com o mesmo nome-base é ambíguo,
    pulado e logado, nunca adivinhado (regra do projeto: nenhum erro
    silencioso).

    `hide_source=True` some a imagem da grade (reversível, mesmo flag
    `hidden` do drag-and-drop manual) — separado do `hide_preview_source`
    do fluxo manual porque este roda em lote, sem ninguém pra responder um
    diálogo "ocultar origem?" no meio da varredura.

    Retorna quantas capas foram criadas.
    """
    from pathlib import Path

    from assetdeck.db.repos import assets as assets_repo
    from assetdeck.db.repos import previews as previews_repo
    from assetdeck.thumbs.preview import can_preview

    # Modelos sem capa, indexados por (pasta, nome-base em minúsculas).
    modelos: dict[tuple[str, str], tuple[int, str]] = {}
    for row in conn.execute(
        f"""SELECT a.id, f.rel_path FROM assets a
            JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})
              AND NOT EXISTS (SELECT 1 FROM previews p
                              WHERE p.asset_id = a.id AND p.is_cover = 1
                                AND p.deleted_at IS NULL)""",
        (library_id, *OWNER_TYPES),
    ):
        rel = row["rel_path"]
        modelos[(_dir_of(rel), Path(rel).stem.lower())] = (row["id"], rel)

    if not modelos:
        return 0

    # Imagens candidatas, agrupadas pela MESMA chave (pasta, nome-base) —
    # o próprio arquivo do modelo nunca bate aqui: `can_preview` é falso
    # pra .blend/.fbx/.obj.
    candidatos: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for row in conn.execute(
        """SELECT f.rel_path, a.id AS asset_id FROM files f
           JOIN assets a ON a.id = f.asset_id
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
        (library_id,),
    ):
        rel = row["rel_path"]
        p = Path(rel)
        chave = (_dir_of(rel), p.stem.lower())
        if chave in modelos and can_preview(p):
            candidatos.setdefault(chave, []).append((rel, row["asset_id"]))

    criadas = 0
    for chave, itens in candidatos.items():
        if len(itens) != 1:
            log.info("Preview por nome ambíguo em %r: %d candidatos — pulado (%s).",
                     chave, len(itens), ", ".join(rel for rel, _aid in itens))
            continue
        rel_imagem, imagem_asset_id = itens[0]
        asset_id, _modelo_rel = modelos[chave]
        try:
            previews_repo.add(conn, asset_id, Path(library_root) / rel_imagem,
                              Path(previews_dir), origin="auto")
            criadas += 1
            if hide_source:
                assets_repo.set_hidden(conn, imagem_asset_id, True)
        except (OSError, FileNotFoundError):
            log.warning("Preview por nome ilegível: %s", rel_imagem, exc_info=True)

    if criadas:
        log.info("Capas automáticas por nome: %d modelos ganharam preview.", criadas)
    return criadas
