"""Aplica as migrations em ordem. O banco sabe em que versão está."""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    MIGRATIONS_DIR = Path(sys._MEIPASS) / "assetdeck" / "db" / "migrations"
else:
    MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME_RE = re.compile(r"^(\d{3})_.+\.sql$")


def current_version(conn: sqlite3.Connection) -> int:
    """Versão aplicada mais alta; 0 se o banco é novo."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version    INTEGER PRIMARY KEY,
               name       TEXT NOT NULL,
               applied_at TEXT NOT NULL
           )"""
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 0


def pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, Path]]:
    """Migrations no disco com versão maior que a do banco, em ordem."""
    applied = current_version(conn)
    found: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _NAME_RE.match(path.name)
        if not m:
            raise RuntimeError(
                f"Migration com nome inválido: {path.name!r}. "
                "O padrão é NNN_descricao.sql (ex.: 001_initial.sql)."
            )
        version = int(m.group(1))
        if version > applied:
            found.append((version, path))
    return found


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Aplica todas as migrations pendentes. Retorna a versão final do banco."""
    for version, path in pending_migrations(conn):
        log.info("Aplicando migration %03d (%s)…", version, path.name)
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
        except sqlite3.Error as exc:
            # Sem except silencioso: contexto completo no log e erro legível.
            log.exception("Falha ao aplicar %s", path.name)
            raise RuntimeError(
                f"A migration {path.name} falhou: {exc}. "
                "O banco pode estar incompleto — veja o log para detalhes."
            ) from exc
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, path.name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        log.info("Migration %03d aplicada.", version)
    return current_version(conn)
