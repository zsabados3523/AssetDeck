"""Separa o trabalho que alguém está ESPERANDO ver do trabalho de fundo.

Motivo (achado investigando o relato do Rafael "cliquei duas vezes num
.blend e num .hdr e não abre nada", 2026-08-19): tudo usava o MESMO
`QThreadPool.globalInstance()` — as miniaturas da grade E a carga do
visualizador. Numa biblioteca de 102 mil assets, a abertura do app agenda
centenas de miniaturas de uma vez (564 na sessão dele, cada HDRI 4K
levando ~0,76s), e as células visíveis ainda entram com prioridade 1,
FURANDO a fila. A carga do visualizador entrava com prioridade padrão, no
fim de tudo: a janela abria em "Carregando…" e podia ficar dezenas de
segundos assim, com a varredura em paralelo empurrando mais miniaturas pra
fila o tempo todo. Do lado de cá parecia que nada abria.

Pior: `ThumbnailPipeline.shutdown()` chamava `clear()` no pool GLOBAL —
descartando de quebra o que o visualizador tivesse pendente.

Regra desde então: **nada que o usuário está esperando na tela divide fila
com trabalho de fundo.**
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThreadPool

log = logging.getLogger(__name__)

# Duas threads: no máximo uma carga de visualizador e uma de prévia ao mesmo
# tempo — abrir um asset é uma coisa de cada vez. O que importa aqui não é
# ter MUITAS threads, é ter uma LIVRE na hora do clique.
_MAX_INTERATIVO = 2

_pool: QThreadPool | None = None


def interativo() -> QThreadPool:
    """Pool das cargas que alguém está esperando: visualizador 3D e prévia.

    Nunca é o pool global — é justamente essa separação que garante uma
    thread livre no instante do duplo clique, por mais cheia que esteja a
    fila das miniaturas.
    """
    global _pool
    if _pool is None:
        _pool = QThreadPool()
        _pool.setMaxThreadCount(_MAX_INTERATIVO)
        log.info("Pool interativo criado (%d threads, separado do global).",
                 _MAX_INTERATIVO)
    return _pool
