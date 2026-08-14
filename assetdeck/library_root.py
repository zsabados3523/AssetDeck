"""Onde está a biblioteca — e o que fazer quando ela sai do lugar.

Motivo (bug real, 2026-08-09): o SSD do Rafael é montado automaticamente
pelo sistema, e o ponto de montagem MUDA entre sessões. A biblioteca estava
gravada em `/media/rafael/SSD/...` e num belo dia o mesmo disco apareceu em
`/mnt/284A670E4A66D7D8/...`. O app abria normalmente (as miniaturas já
estavam em cache), a grade parecia inteira, e só quebrava na hora de LER um
arquivo original — arrastar uma imagem para virar preview de um modelo
falhava com `FileNotFoundError` que só aparecia no log. Da tela, "não
acontecia nada".

Este módulo faz duas coisas:

1. `resolve()` — dado o caminho gravado, diz se ele existe; se não existe,
   procura a MESMA biblioteca nos outros pontos de montagem do sistema.
2. `repoint()` — grava o caminho novo nos DOIS lugares que o guardam
   (config.json e a linha da tabela `libraries`). Tem de ser nos dois: só o
   config faria `libraries.get_or_create` criar uma biblioteca NOVA e vazia,
   e a grade do Rafael (72 mil assets) sumiria da tela.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Onde o Linux costuma montar disco externo. `/media/<user>` é o padrão do
# udisks (GNOME), `/run/media/<user>` o de distros com systemd puro, e
# `/mnt` é onde caem montagens manuais e de alguns gerenciadores de arquivo.
def _mount_roots() -> list[Path]:
    roots: list[Path] = []
    for base in (Path("/media"), Path("/run/media")):
        if not base.is_dir():
            continue
        # /media/<user>/<label> — junta os dois níveis
        roots.extend(_subdirs(base))
        for user_dir in _subdirs(base):
            roots.extend(_subdirs(user_dir))
    roots.extend(_subdirs(Path("/mnt")))
    return roots


def _subdirs(base: Path) -> list[Path]:
    """Subpastas de `base`, sem explodir se ela não puder ser lida.

    Ponto de montagem quebrado (disco removido no meio do caminho) levanta
    OSError no `iterdir` — isso é informação, não motivo para derrubar o app.
    """
    try:
        return [p for p in base.iterdir() if p.is_dir()]
    except OSError as exc:
        log.info("Não consegui listar %s ao procurar a biblioteca: %s", base, exc)
        return []


@dataclass(frozen=True)
class Resolution:
    """Resultado de procurar a biblioteca."""

    configured: Path
    found: Path | None

    @property
    def ok(self) -> bool:
        """A biblioteca está exatamente onde o config diz."""
        return self.found == self.configured

    @property
    def moved(self) -> bool:
        """Achei a biblioteca, mas em outro ponto de montagem."""
        return self.found is not None and self.found != self.configured

    @property
    def missing(self) -> bool:
        """Não achei a biblioteca em lugar nenhum."""
        return self.found is None


def resolve(configured: Path) -> Resolution:
    """Confere o caminho gravado e, se ele não existir, procura a biblioteca
    nos pontos de montagem do sistema.

    A busca casa o FINAL do caminho: de
    `/media/rafael/SSD/Documentos/{cura}/BIBLIOTECA {CURA}` sobra
    `Documentos/{cura}/BIBLIOTECA {CURA}` para pendurar em cada ponto de
    montagem candidato. Vence o sufixo MAIS LONGO que existir — quanto mais
    pedaços do caminho batem, menor a chance de ser coincidência.
    """
    configured = Path(configured)
    if configured.is_dir():
        return Resolution(configured=configured, found=configured)

    log.warning("Biblioteca não está no caminho gravado: %s", configured)

    partes = configured.parts
    if partes and partes[0] == "/":
        partes = partes[1:]

    candidatos = _mount_roots()
    log.info("Procurando a biblioteca em %d ponto(s) de montagem: %s",
             len(candidatos), [str(c) for c in candidatos])

    # k=0 é o sufixo mais longo (o caminho inteiro sem a barra inicial);
    # quanto maior o k, menos específico. O primeiro que existir vence.
    for k in range(len(partes)):
        sufixo = Path(*partes[k:])
        for raiz in candidatos:
            alvo = raiz / sufixo
            if alvo.is_dir():
                log.info("Biblioteca encontrada em outro lugar: %s (era %s)",
                         alvo, configured)
                return Resolution(configured=configured, found=alvo)

    log.error("Biblioteca não encontrada em nenhum ponto de montagem: %s", configured)
    return Resolution(configured=configured, found=None)


def repoint(conn: sqlite3.Connection, old_root: Path, new_root: Path) -> int:
    """Aponta a biblioteca para `new_root` na tabela `libraries`.

    Devolve quantas linhas foram atualizadas. Só mexe em `root_path` — os
    assets guardam caminho RELATIVO (`rel_path`), então nada mais precisa
    mudar. Quem grava o config.json é o chamador (`config.save_config`),
    porque este módulo não decide política, só executa.
    """
    cur = conn.execute(
        "UPDATE libraries SET root_path = ? WHERE root_path = ? AND deleted_at IS NULL",
        (str(new_root), str(old_root)),
    )
    conn.commit()
    log.info("libraries.root_path: %s -> %s (%d linha(s))", old_root, new_root, cur.rowcount)
    return cur.rowcount
