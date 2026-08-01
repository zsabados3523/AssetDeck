"""Instalação do add-on na pasta do Blender (o AssetDeck faz por você).

Descobre o caminho de add-ons do Blender Flatpak, copia o pacote e grava o
bridge_config.json com host/porta/token. Reinstalar é sempre seguro:
substitui a versão anterior.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from assetdeck.bridge import protocol as proto

log = logging.getLogger(__name__)

ADDON_NAME = "assetdeck_bridge"
# Caminho do Blender instalado por Flatpak (verificado no 5.2 do Rafael)
FLATPAK_CONFIG = Path.home() / ".var/app/org.blender.Blender/config/blender"


def source_dir() -> Path:
    """Onde mora o código-fonte do add-on dentro do projeto."""
    return Path(__file__).resolve().parents[2] / "blender_addon" / ADDON_NAME


def find_addon_dirs() -> list[Path]:
    """Pastas scripts/addons de cada versão do Blender Flatpak encontrada.

    Retorna da versão mais nova para a mais antiga.
    """
    if not FLATPAK_CONFIG.is_dir():
        return []
    versoes = []
    for d in FLATPAK_CONFIG.iterdir():
        try:
            versoes.append((tuple(int(p) for p in d.name.split(".")), d))
        except ValueError:
            continue  # pastas que não são "5.2", "4.2"…
    return [d / "scripts" / "addons" for _v, d in sorted(versoes, reverse=True)]


def install(token: str, port: int = proto.DEFAULT_PORT,
            host: str = proto.DEFAULT_HOST) -> list[Path]:
    """Copia o add-on para TODAS as versões do Blender encontradas.

    Retorna os destinos instalados. Levanta RuntimeError com mensagem
    legível se não achar o Blender ou o código-fonte.
    """
    origem = source_dir()
    if not origem.is_dir():
        raise RuntimeError(
            f"Código do add-on não encontrado em {origem}. "
            "O projeto está incompleto?"
        )
    destinos_base = find_addon_dirs()
    if not destinos_base:
        raise RuntimeError(
            "Não encontrei o Blender instalado por Flatpak. Instale com "
            "'flatpak install flathub org.blender.Blender' e abra o Blender "
            "uma vez antes de instalar o add-on."
        )

    instalados: list[Path] = []
    for base in destinos_base:
        destino = base / ADDON_NAME
        base.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            shutil.rmtree(destino)  # remove só a versão antiga DO NOSSO add-on
        shutil.copytree(origem, destino,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (destino / "bridge_config.json").write_text(
            json.dumps({"host": host, "port": port, "token": token}, indent=2),
            encoding="utf-8",
        )
        instalados.append(destino)
        log.info("Add-on instalado em %s", destino)
    return instalados
