"""Cliente socket do add-on. Sem dependências além da stdlib do Blender."""

from __future__ import annotations

import json
import os
import socket

CONFIG_NAME = "bridge_config.json"
TIMEOUT_S = 5.0


class BridgeError(Exception):
    """Erro legível para mostrar ao Rafael dentro do Blender."""


def _config() -> dict:
    """Lê host/porta/token gravados pelo AssetDeck ao instalar o add-on."""
    caminho = os.path.join(os.path.dirname(__file__), CONFIG_NAME)
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise BridgeError(
            "Configuração da ponte não encontrada. Reinstale o add-on pelo "
            "AssetDeck (menu Blender → Instalar/atualizar add-on)."
        ) from None
    except (json.JSONDecodeError, OSError) as exc:
        raise BridgeError(f"Configuração da ponte ilegível: {exc}") from exc


def request(payload: dict) -> dict:
    """Envia um comando e devolve a resposta. Levanta BridgeError legível."""
    cfg = _config()
    payload = {**payload, "token": cfg.get("token", "")}
    try:
        with socket.create_connection(
            (cfg.get("host", "127.0.0.1"), int(cfg.get("port", 45017))),
            timeout=TIMEOUT_S,
        ) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            pedaços = bytearray()
            while b"\n" not in pedaços:
                bloco = sock.recv(65536)
                if not bloco:
                    break
                pedaços.extend(bloco)
    except ConnectionRefusedError:
        raise BridgeError(
            "O AssetDeck não está aberto (ou a ponte está desligada). "
            "Abra o AssetDeck e tente de novo."
        ) from None
    except socket.timeout:
        raise BridgeError("O AssetDeck demorou demais para responder.") from None
    except OSError as exc:
        raise BridgeError(f"Falha de conexão com o AssetDeck: {exc}") from exc

    linha = bytes(pedaços).split(b"\n", 1)[0]
    if not linha:
        raise BridgeError("O AssetDeck fechou a conexão sem responder.")
    try:
        resposta = json.loads(linha.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BridgeError(f"Resposta ilegível do AssetDeck: {exc}") from exc

    if not resposta.get("ok"):
        raise BridgeError(resposta.get("error", "Erro desconhecido no AssetDeck."))
    return resposta
