"""Caminhos do app (padrão XDG) e configuração em JSON.

Tudo pode ser sobrescrito por variável de ambiente — é assim que os testes
usam pastas temporárias sem tocar nos dados reais (mock só em teste).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "assetdeck"

# Valores criados no config.json na primeira execução.
# A raiz da biblioteca é CONFIGURAÇÃO (editável no json), nunca hardcoded no app.
DEFAULTS = {
    "library_root": "/home/rafael/00 - PROJETOS/assetdeck-testlib",
    "backup_keep": 14,  # quantos backups diários do .db manter
}


def _dir_from_env(env_var: str, xdg_var: str, fallback: str) -> Path:
    """Resolve um diretório: env do app > variável XDG > padrão do sistema."""
    if os.environ.get(env_var):
        return Path(os.environ[env_var])
    base = Path(os.environ.get(xdg_var, "")) if os.environ.get(xdg_var) else Path.home() / fallback
    return base / APP_NAME


def config_dir() -> Path:
    return _dir_from_env("ASSETDECK_CONFIG_DIR", "XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _dir_from_env("ASSETDECK_DATA_DIR", "XDG_DATA_HOME", ".local/share")


def cache_dir() -> Path:
    return _dir_from_env("ASSETDECK_CACHE_DIR", "XDG_CACHE_HOME", ".cache")


def db_path() -> Path:
    return data_dir() / "assetdeck.db"


def backups_dir() -> Path:
    return data_dir() / "backups"


def logs_dir() -> Path:
    return data_dir() / "logs"


def thumbs_dir() -> Path:
    return cache_dir() / "thumbs"


def ensure_dirs() -> None:
    """Cria todas as pastas do app se não existirem."""
    for d in (config_dir(), data_dir(), cache_dir(), backups_dir(), logs_dir(), thumbs_dir()):
        d.mkdir(parents=True, exist_ok=True)


def config_file() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    """Lê o config.json, criando-o com os padrões na primeira execução.

    Se o arquivo estiver corrompido, ele é preservado com sufixo .broken-<ts>
    (nada é perdido) e um novo é criado com os padrões — tudo logado.
    """
    path = config_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("config.json criado com padrões em %s", path)
        return dict(DEFAULTS)

    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        broken = path.with_name(f"config.json.broken-{int(time.time())}")
        path.rename(broken)
        log.error(
            "config.json inválido (%s). Arquivo preservado em %s; recriando com padrões.",
            exc, broken,
        )
        return load_config()

    # Completa chaves que faltarem (config antigo + padrões novos)
    merged = {**DEFAULTS, **cfg}
    return merged
