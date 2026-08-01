"""Batch rename (Fatia 23) — A ÚNICA EXCEÇÃO ao somente-leitura do app.

Fica na raiz do pacote de propósito: é a única operação que toca em
arquivos reais da biblioteca (fora da criação de sidecars), então precisa
ficar visível, não escondida dentro de `db/` ou `indexer/`.

Busca-e-substituição aplicada ao NOME de cada arquivo ativo (não sumido)
das assets selecionadas — inclusive todos os mapas de um set PBR, um por
um, preservando o que não bate com a busca (o sufixo do papel continua
intacto). Sempre em duas fases: `build_plan`/`find_conflicts` (prévia, só
leitura) e `apply_plan` (escreve, só depois de confirmação explícita na
UI). Um arquivo que falhar não derruba o lote inteiro.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RenamePlanItem:
    file_id: int
    asset_id: int
    old_rel_path: str
    new_rel_path: str


def build_plan(
    conn: sqlite3.Connection, asset_ids: list[int], busca: str, substitui: str
) -> list[RenamePlanItem]:
    """Prévia: troca `busca` por `substitui` só no NOME (não na pasta) de
    todo arquivo ativo e não sumido das assets selecionadas. Só entram os
    que realmente mudam pra um nome não-vazio."""
    if not busca or not asset_ids:
        return []
    marks = ",".join("?" * len(asset_ids))
    rows = conn.execute(
        f"""SELECT id, asset_id, rel_path FROM files
            WHERE asset_id IN ({marks}) AND deleted_at IS NULL
              AND missing_since IS NULL""",
        asset_ids,
    ).fetchall()

    plano: list[RenamePlanItem] = []
    for r in rows:
        pasta, _, nome = r["rel_path"].rpartition("/")
        novo_nome = nome.replace(busca, substitui)
        if novo_nome == nome or not Path(novo_nome).stem.strip():
            continue
        novo_rel = f"{pasta}/{novo_nome}" if pasta else novo_nome
        plano.append(RenamePlanItem(r["id"], r["asset_id"], r["rel_path"], novo_rel))
    return plano


def find_conflicts(
    conn: sqlite3.Connection, library_id: int, plano: list[RenamePlanItem]
) -> dict[str, str]:
    """Novo caminho que colide → motivo. Cobre: dois itens do lote gerando
    o mesmo nome, e um novo nome que já existe como arquivo ativo FORA do
    lote. (Colidir com o nome ATUAL de outro arquivo que TAMBÉM está no
    lote não é bloqueado aqui — se a ordem de aplicação não ajudar, só
    aquele item falha sozinho em `apply_plan`, sem travar o resto; não vale
    a complexidade de resolver cadeias de rename pra este uso.)"""
    conflitos: dict[str, str] = {}
    novos: dict[str, int] = {}
    for item in plano:
        if item.new_rel_path in novos:
            conflitos[item.new_rel_path] = "duas entradas do lote geram o mesmo nome"
        novos[item.new_rel_path] = item.file_id

    if not novos:
        return conflitos
    marks = ",".join("?" * len(novos))
    existentes = conn.execute(
        f"""SELECT f.id, f.rel_path FROM files f JOIN assets a ON a.id = f.asset_id
            WHERE a.library_id = ? AND f.deleted_at IS NULL
              AND f.rel_path IN ({marks})""",
        [library_id, *novos.keys()],
    ).fetchall()
    ids_do_lote = {item.file_id for item in plano}
    for r in existentes:
        if r["id"] not in ids_do_lote:
            conflitos.setdefault(r["rel_path"], "já existe um arquivo com esse nome")
    return conflitos


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_plan(
    conn: sqlite3.Connection, library_root: Path, plano: list[RenamePlanItem]
) -> tuple[int, int]:
    """Executa de fato: renomeia no disco (sidecar junto, se houver) e
    atualiza rel_path no banco. Item problemático é pulado e logado — não
    derruba o lote. Devolve (sucesso, falhas)."""
    sucesso = falhas = 0
    now = _now()
    for item in plano:
        old_abs = library_root / item.old_rel_path
        new_abs = library_root / item.new_rel_path
        try:
            if not old_abs.is_file():
                raise FileNotFoundError(f"arquivo sumiu antes do rename: {old_abs}")
            if new_abs.exists():
                raise FileExistsError(f"já existe um arquivo em {new_abs}")
            old_abs.rename(new_abs)
        except OSError:
            log.exception("Renomear falhou: %s -> %s — pulando.", old_abs, new_abs)
            falhas += 1
            continue

        old_sidecar = old_abs.with_name(old_abs.name + ".assetdeck.json")
        if old_sidecar.is_file():
            new_sidecar = new_abs.with_name(new_abs.name + ".assetdeck.json")
            try:
                old_sidecar.rename(new_sidecar)
            except OSError:
                log.warning("Sidecar não acompanhou o rename de %s (fica órfão).",
                            old_abs, exc_info=True)

        conn.execute(
            "UPDATE files SET rel_path = ?, updated_at = ? WHERE id = ?",
            (item.new_rel_path, now, item.file_id),
        )
        sucesso += 1
        log.info("Renomeado: %s -> %s", item.old_rel_path, item.new_rel_path)

    conn.commit()
    log.info("Batch rename concluído: %d sucesso(s), %d falha(s).", sucesso, falhas)
    return sucesso, falhas
