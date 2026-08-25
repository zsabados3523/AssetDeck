"""Logging do app: arquivo rotativo + console, erros sempre com contexto.

Também liga o `faulthandler` (ver `armar_rastreador_de_quedas`): quando o
processo cai por falha de segmentação — coisa que acontece com Qt/OpenGL e
NÃO deixa traceback nenhum —, é a única forma de saber onde ele estava.
"""

from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Mantido vivo pelo processo inteiro DE PROPÓSITO: o `faulthandler` guarda o
# descritor, e um arquivo coletado pelo Python fecharia o descritor justamente
# antes da hora em que ele é necessário.
_arquivo_de_quedas = None


def armar_rastreador_de_quedas(logs_dir: Path) -> Path | None:
    """Faz uma queda de nível C++ deixar a pilha do Python em disco.

    **Por que existe** (2026-08-23): o Rafael relatou "o programa
    simplesmente fecha" ao mexer em tags. Não havia traceback no log — não
    era exceção do Python —, nem morte por falta de memória. Numa queda
    dessas o Qt derruba o processo e não sobra nada pra investigar; o que o
    `faulthandler` escreve é a pilha Python do instante da falha.

    O arquivo é o mesmo entre execuções, em modo de APÊNDICE: uma queda que
    só acontece de vez em quando não pode depender de alguém estar com uma
    instância instrumentada no ar na hora certa. Na primeira vez custou uma
    reprodução perdida — o registro estava em `/tmp` e a limpeza do sistema
    o apagou antes de eu ler.
    """
    global _arquivo_de_quedas

    destino = logs_dir / "quedas.txt"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        _arquivo_de_quedas = open(destino, "a", encoding="utf-8")
        _arquivo_de_quedas.write(
            f"\n===== AssetDeck iniciado em {os.getpid()} =====\n")
        _arquivo_de_quedas.flush()
        faulthandler.enable(file=_arquivo_de_quedas, all_threads=True)
        return destino
    except OSError:
        # Sem rastreador o app funciona igual — não é motivo pra não abrir.
        logging.getLogger(__name__).warning(
            "Não consegui armar o rastreador de quedas em %s.", destino,
            exc_info=True)
        return None


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
    log = logging.getLogger(__name__)
    log.info("Logging iniciado (nível %s) — arquivo em %s",
             level_name, logs_dir / "assetdeck.log")

    quedas = armar_rastreador_de_quedas(logs_dir)
    if quedas is not None:
        log.info("Rastreador de quedas armado — pilha vai para %s.", quedas)
