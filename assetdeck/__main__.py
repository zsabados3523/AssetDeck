"""Ponto de entrada: python -m assetdeck [--screenshot PATH]"""

from __future__ import annotations

import logging
import sys

from assetdeck.app import run


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Exception:
        # Último recurso: loga o traceback completo e fala com o usuário
        # em português claro. Nenhum erro morre em silêncio.
        logging.getLogger("assetdeck").exception("Erro fatal na inicialização")
        print(
            "\nO AssetDeck encontrou um erro e não pôde abrir.\n"
            "O detalhe técnico foi gravado no log "
            "(~/.local/share/assetdeck/logs/assetdeck.log).\n"
            "Cole a mensagem acima na conversa com o Claude para investigarmos.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
