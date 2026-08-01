"""Protocolo da ponte AssetDeck ↔ Blender.

Uma mensagem = um JSON em UMA linha, terminada por \\n. Simples de depurar
(dá para testar com telnet) e sem dependências.

Só escuta em 127.0.0.1 e exige um token — nenhum outro processo local
conversa com o AssetDeck por acidente. Nada sai da máquina.
"""

from __future__ import annotations

import json

VERSION = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 45017

# Comandos aceitos nesta fatia
CMD_PING = "ping"
CMD_LIST_ASSETS = "list_assets"
CMD_GET_ASSET = "get_asset"

KNOWN_COMMANDS = {CMD_PING, CMD_LIST_ASSETS, CMD_GET_ASSET}

MAX_MESSAGE_BYTES = 256 * 1024  # trava contra mensagem malformada infinita


def encode(payload: dict) -> bytes:
    """dict → linha JSON pronta para o socket."""
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict:
    """Linha JSON → dict. Levanta ValueError se não for um objeto válido."""
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("Mensagem deve ser um objeto JSON.")
    return data


def ok(**fields) -> dict:
    return {"ok": True, **fields}


def error(message: str, code: str = "error") -> dict:
    return {"ok": False, "code": code, "error": message}
