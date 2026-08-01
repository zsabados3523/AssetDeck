"""Cache de thumbnails em disco, chaveado pelo conteúdo do arquivo.

A chave é o content_hash do arquivo original: se o arquivo mudar, o hash muda
e a thumbnail é regenerada sozinha; se nada mudou, a segunda abertura do app
é instantânea.
"""

from __future__ import annotations

from pathlib import Path

THUMB_SIZE = 256

# Versão do FORMATO da thumbnail. Subir este número invalida o cache inteiro
# de uma vez (as antigas ficam órfãs e as novas são geradas em background).
# v2: cutouts sobre xadrez + HDR/EXR tonemapados (Fatia 7).
# v3: cutouts com transparência REAL, sem xadrez (feedback do Rafael, Fatia 8).
THUMB_VERSION = 3


def thumb_path(thumbs_dir: Path, content_hash: str, size: int = THUMB_SIZE) -> Path:
    """Onde a thumbnail deste conteúdo vive (exista ela ou não)."""
    return thumbs_dir / f"{content_hash}_{size}_v{THUMB_VERSION}.png"
