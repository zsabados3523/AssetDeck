"""Conexão SQLite: WAL, foreign keys ligadas, timeouts amigáveis."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


def connect(db_path: Path) -> sqlite3.Connection:
    """Abre (ou cria) o banco com os pragmas do projeto.

    - WAL: leitura concorrente com escrita (UI lê enquanto o indexer grava).
    - foreign_keys ON: o SQLite só valida FKs se pedirmos explicitamente.
    - busy_timeout: espera em vez de falhar se outra thread estiver escrevendo.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    log.debug("Banco aberto em %s", db_path)
    return conn
