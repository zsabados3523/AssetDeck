"""Purga de previews órfãos (Fatia 104).

A pasta ``~/.local/share/assetdeck/previews/`` guarda as CÓPIAS de imagem
que o app faz quando você escolhe um preview (``previews_repo.add``).
``previews_repo.soft_delete`` tira a linha da galeria mas nunca apagou o
arquivo — meses de "assinalar previews por nome" (Fatias 57/81/84/101) e
troca de capa deixaram milhares de arquivos que nenhuma linha ativa
referencia.

Isto NÃO é a biblioteca: ``previews/`` é dado gerenciado do app, recriável
(igual ``thumbs/``). Apagar órfão daqui não abre exceção nova ao
somente-leitura. Mesmo assim segue o padrão do projeto: ``planejar`` não
toca em disco, a UI mostra o que some e confirma, e ``executar`` loga cada
arquivo e não derruba o lote se um ``unlink`` falhar.

Arquivo cujo ``file_path`` de linha ATIVA aponta para FORA de ``previews/``
(imagem escolhida direto pelo usuário, nunca copiada) jamais entra na
lista — hoje não existe nenhuma linha assim, mas o código não assume isso.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Só apagamos arquivos com cara de cópia de preview. Qualquer outra coisa
# que apareça na pasta (um .db, um .json, um .tmp de escrita interrompida)
# fica onde está.
_EXTS_PREVIEW = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp",
    ".tif", ".tiff", ".gif", ".tga", ".exr", ".hdr",
}


@dataclass(frozen=True)
class PlanoPurga:
    """Prévia da purga — nada foi apagado ainda."""

    orfaos: list[Path]
    bytes_orfaos: int
    arquivos_em_uso: int
    bytes_em_uso: int

    @property
    def total_orfaos(self) -> int:
        return len(self.orfaos)

    @property
    def bytes_totais(self) -> int:
        return self.bytes_orfaos + self.bytes_em_uso


def _resolver(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def _referenciados(conn: sqlite3.Connection, previews_dir: Path) -> set[Path]:
    """Caminhos resolvidos, DENTRO de ``previews_dir``, citados por qualquer
    linha ativa de ``previews`` (``deleted_at IS NULL``)."""
    ref: set[Path] = set()
    for row in conn.execute(
        "SELECT file_path FROM previews WHERE deleted_at IS NULL"
    ):
        alvo = _resolver(Path(row["file_path"]))
        try:
            alvo.relative_to(previews_dir)
        except ValueError:
            continue  # aponta pra fora da pasta do app — nunca é candidato
        ref.add(alvo)
    return ref


def planejar(conn: sqlite3.Connection, previews_dir: Path) -> PlanoPurga:
    """Varre ``previews_dir`` e separa órfão (nenhuma linha ativa usa) de
    arquivo em uso. Não toca em disco."""
    previews_dir = _resolver(Path(previews_dir))
    if not previews_dir.is_dir():
        return PlanoPurga([], 0, 0, 0)

    referenciados = _referenciados(conn, previews_dir)

    orfaos: list[Path] = []
    bytes_orfaos = arquivos_em_uso = bytes_em_uso = 0
    for arq in sorted(previews_dir.iterdir()):
        if not arq.is_file() or arq.suffix.lower() not in _EXTS_PREVIEW:
            continue
        try:
            tam = arq.stat().st_size
        except OSError:
            log.warning("previews: não consegui ler %s ao planejar a purga",
                        arq, exc_info=True)
            continue
        if _resolver(arq) in referenciados:
            arquivos_em_uso += 1
            bytes_em_uso += tam
        else:
            orfaos.append(arq)
            bytes_orfaos += tam

    log.info(
        "previews: purga planejada — %d órfãos (%d bytes), %d em uso (%d bytes)",
        len(orfaos), bytes_orfaos, arquivos_em_uso, bytes_em_uso,
    )
    return PlanoPurga(orfaos, bytes_orfaos, arquivos_em_uso, bytes_em_uso)


def executar(plano: PlanoPurga) -> tuple[int, int, int]:
    """Apaga os órfãos do plano. Retorna ``(apagados, bytes_liberados,
    falhas)``. Cada falha é logada com contexto; o lote continua."""
    apagados = bytes_liberados = falhas = 0
    for arq in plano.orfaos:
        try:
            tam = arq.stat().st_size
            arq.unlink()
        except OSError:
            falhas += 1
            log.warning("previews: falha ao apagar órfão %s", arq, exc_info=True)
            continue
        apagados += 1
        bytes_liberados += tam
    log.info(
        "previews: purga concluída — %d apagados (%d bytes liberados), %d falhas",
        apagados, bytes_liberados, falhas,
    )
    return apagados, bytes_liberados, falhas
