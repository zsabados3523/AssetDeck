"""Cache de thumbnails em disco, chaveado pelo conteúdo do arquivo.

A chave é o content_hash do arquivo original: se o arquivo mudar, o hash muda
e a thumbnail é regenerada sozinha; se nada mudou, a segunda abertura do app
é instantânea.
"""

from __future__ import annotations

from pathlib import Path

THUMB_SIZE = 256


def thumb_path(thumbs_dir: Path, content_hash: str, size: int = THUMB_SIZE) -> Path:
    """Onde a thumbnail deste conteúdo vive (exista ela ou não)."""
    return thumbs_dir / f"{content_hash}_{size}.png"
