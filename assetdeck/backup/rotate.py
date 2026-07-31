"""Backup rotativo diário do banco.

Proteção contra o cenário-Connecter: se o .db corromper, existe uma cópia
de cada um dos últimos N dias em backups/. A cópia usa a API de backup do
SQLite, que é consistente mesmo com o banco aberto em WAL.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

# Só arquivos neste padrão são geridos (criados/podados) por este módulo.
_BACKUP_RE = re.compile(r"^assetdeck-(\d{4}-\d{2}-\d{2})\.db$")


def daily_backup(db_path: Path, backups_dir: Path, keep: int = 14) -> Path | None:
    """Garante um backup do dia. Retorna o caminho criado, ou None se já havia.

    Depois de criar, poda os mais antigos mantendo os `keep` mais recentes.
    Arquivos que não casam o padrão de nome nunca são tocados.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"assetdeck-{date.today().isoformat()}.db"
    if target.exists():
        log.debug("Backup de hoje já existe: %s", target)
        return None

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    except sqlite3.Error:
        log.exception("Falha ao criar backup em %s", target)
        dst.close()
        # Não deixar um backup pela metade no disco:
        if target.exists():
            target.unlink()
        raise
    finally:
        src.close()
        dst.close()
    log.info("Backup diário criado: %s (%d bytes)", target, target.stat().st_size)

    _prune(backups_dir, keep)
    return target


def _prune(backups_dir: Path, keep: int) -> None:
    """Remove os backups mais antigos além dos `keep` mais novos."""
    backups = sorted(
        p for p in backups_dir.iterdir() if _BACKUP_RE.match(p.name)
    )  # nome = data ISO, então ordem alfabética == ordem cronológica
    for old in backups[:-keep] if keep > 0 else backups:
        old.unlink()
        log.info("Backup antigo removido na rotação: %s", old.name)
