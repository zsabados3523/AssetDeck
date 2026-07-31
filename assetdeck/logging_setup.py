"""Logging do app: arquivo rotativo + console, erros sempre com contexto."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(logs_dir: Path) -> None:
    """Configura o logger raiz. Nível via ASSETDECK_LOG_LEVEL (padrão INFO)."""
    level_name = os.environ.get("ASSETDECK_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "assetdeck.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    console_handler = logging.StreamHandler()

    logging.basicConfig(level=level, format=FORMAT, handlers=[file_handler, console_handler])
    logging.getLogger(__name__).info("Logging iniciado (nível %s) — arquivo em %s",
                                     level_name, logs_dir / "assetdeck.log")
