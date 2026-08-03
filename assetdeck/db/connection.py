"""Conexão SQLite: WAL, foreign keys ligadas, timeouts amigáveis."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_distance(hex_a: str | None, hex_b: str | None) -> float | None:
    """Distância euclidiana entre duas cores em hex — usada pelo filtro de
    busca por cor (Fatia 39). `None` se qualquer lado não tiver cor
    calculada (arquivo não-raster) ou vier corrompido — o filtro trata isso
    como "não bate", nunca derruba a query inteira."""
    if hex_a is None or hex_b is None:
        return None
    try:
        r1, g1, b1 = _hex_to_rgb(hex_a)
        r2, g2, b2 = _hex_to_rgb(hex_b)
    except (ValueError, TypeError):
        log.warning("Cor em hex inválida no banco ao comparar %r com %r", hex_a, hex_b)
        return None
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def connect(db_path: Path) -> sqlite3.Connection:
    """Abre (ou cria) o banco com os pragmas do projeto.

    - WAL: leitura concorrente com escrita (UI lê enquanto o indexer grava).
    - foreign_keys ON: o SQLite só valida FKs se pedirmos explicitamente.
    - busy_timeout: espera em vez de falhar se outra thread estiver escrevendo.
    - color_distance: função SQL customizada pro filtro de busca por cor
      (Fatia 39) — comparar hex vira aritmética, não dá pra fazer só com
      SQL puro sem ficar ilegível.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.create_function("color_distance", 2, _color_distance, deterministic=True)
    log.debug("Banco aberto em %s", db_path)
    return conn
