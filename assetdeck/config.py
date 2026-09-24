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
    # claro | escuro — trocado pelo menu Configurações. Padrão virou "escuro"
    # na Fatia 44: a direção visual que o Rafael escolheu olhando os mockups é
    # a de base escura. Quem já tem um config.json não é afetado (o valor
    # gravado ganha do DEFAULT) — isto vale só pra primeira execução.
    "theme_mode": "escuro",
    # Interrompe a animação de hover dos cards; todas as ações continuam
    # funcionando sem movimento transitório.
    "reduce_motion": False,
    "backup_keep": 14,  # quantos backups diários do .db manter
    # Ao usar uma imagem da biblioteca como preview de um modelo:
    # "ask" pergunta se oculta a imagem; "always"/"never" lembram a escolha
    "hide_preview_source": "ask",
    # Ponte com o Blender (F2): porta local e token gerado na 1ª execução
    "bridge_enabled": True,
    "bridge_port": 45017,
    "bridge_token": "",
    # Cena de render de capas (Fatia 38) — valores de hoje convertidos pra
    # hex sRGB (o que sai do QColorDialog); blender/render.py converte pra
    # linear antes de plantar no shader.
    "render_bg_color": "#959599",
    "render_bg_strength": 1.8,
    "render_sun_energy": 3.0,
    # Estado de tela entre sessões (Fatia 54) — geometria, splitters,
    # painéis visíveis, tamanho do slider, tags expandidas e filtros
    # ativos. Escrito inteiro por `MainWindow._save_ui_state()` no
    # fechamento; vazio = nunca fechou o app depois desta fatia, usa os
    # padrões hardcoded de sempre.
    "ui_state": {},
    # Assinalar preview automaticamente por nome igual (Fatia 57):
    # 'Cadeira.blend' + 'Cadeira.jpg' na mesma pasta vira capa sozinha.
    # Desligado por padrão — é comportamento novo que mexe em vários
    # assets de uma vez, opt-in.
    "auto_match_previews_by_name": False,
    # Some a imagem usada como preview da grade (reversível em "Mostrar
    # ocultos") — independente do `hide_preview_source` do fluxo manual,
    # porque este roda em lote, sem ninguém pra responder um diálogo.
    "auto_match_hide_source": False,
}


def ensure_bridge_token(cfg: dict) -> str:
    """Garante um token da ponte no config (gera na primeira vez)."""
    import secrets

    if not cfg.get("bridge_token"):
        cfg["bridge_token"] = secrets.token_urlsafe(24)
        save_config(cfg)
        log.info("Token da ponte com o Blender gerado.")
    return cfg["bridge_token"]


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


def models3d_cache_dir() -> Path:
    """.obj exportados de .blend pelo visualizador 3D (Fase 6) — cache por
    content_hash, mesma ideia de `thumbs_dir()` (recriável, nunca é a
    fonte da verdade)."""
    return cache_dir() / "models3d"


def previews_dir() -> Path:
    """Cópias das imagens de preview escolhidas pelo usuário (Fatia 10)."""
    return data_dir() / "previews"


def ensure_dirs() -> None:
    """Cria todas as pastas do app se não existirem."""
    for d in (config_dir(), data_dir(), cache_dir(), backups_dir(), logs_dir(),
              thumbs_dir(), models3d_cache_dir(), previews_dir()):
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


def save_config(cfg: dict) -> None:
    """Regrava o config.json (escrita atômica)."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"config.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    log.info("config.json atualizado.")
