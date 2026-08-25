"""Fila de geração de thumbnails em QThreadPool — a UI nunca espera."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from assetdeck.thumbs.cache import thumb_name, thumb_path
from assetdeck.thumbs.preview import make_any_thumbnail

log = logging.getLogger(__name__)


class _Signaller(QObject):
    ready = Signal(int, str)    # asset_id, caminho da thumb
    failed = Signal(int)        # asset_id


_rebaixada = threading.local()


def rebaixar_esta_thread() -> None:
    """Põe a thread ATUAL em segundo plano (`nice +5`), uma vez só.

    Gerar miniatura é trabalho de fundo: pode demorar, ninguém está olhando.
    Sem isto, as threads do pool disputam núcleo de igual pra igual com o
    que o Rafael estiver fazendo — e a abertura do app, que agenda centenas
    de miniaturas de uma vez, deixava a máquina pesada (relato de
    2026-08-19). Mesmo remédio que os processos da varredura já usam
    (`indexer/scanner.py::_preparar_worker`).

    No Linux `nice()` vale pra THREAD que chama, não pro processo — a UI
    não é afetada. A trava por thread existe porque `nice` é cumulativo: a
    thread do pool atende muitos jobs, e sem ela cada job rebaixaria mais um
    degrau até o fundo do poço.
    """
    if getattr(_rebaixada, "feito", False):
        return
    _rebaixada.feito = True
    try:
        os.nice(5)
    except OSError:
        log.warning("Não consegui baixar a prioridade da thread de miniaturas.",
                    exc_info=True)


class _ThumbJob(QRunnable):
    def __init__(self, signaller: _Signaller, asset_id: int, src: Path, dest: Path) -> None:
        super().__init__()
        self._sig = signaller
        self._asset_id = asset_id
        self._src = src
        self._dest = dest

    def run(self) -> None:
        rebaixar_esta_thread()
        try:
            make_any_thumbnail(self._src, self._dest)
            self._sig.ready.emit(self._asset_id, str(self._dest))
        except Exception:
            # Uma imagem corrompida não pode derrubar o app — mas fica no log.
            log.exception("Thumbnail falhou para %s", self._src)
            self._sig.failed.emit(self._asset_id)


class ThumbnailPipeline(QObject):
    """Pede-se uma thumb; se não existe, é gerada no pool e avisada por sinal."""

    ready = Signal(int, str)   # repassado ao modelo da grid

    def __init__(self, thumbs_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thumbs_dir = thumbs_dir
        # Pool PRÓPRIO e limitado, não o global (achado em 2026-08-19).
        # Dois motivos:
        #
        # 1. O global tem uma thread por núcleo (16 na máquina do Rafael).
        #    Na abertura, com a varredura rodando em mais 4 processos, as
        #    miniaturas tomavam a máquina inteira — é o "uso de CPU sobe
        #    bastante" que ele relatou. Metade dos núcleos mantém a fila
        #    andando e deixa respiro pro resto (varredura, UI, visualizador).
        # 2. `shutdown()` chama `clear()`: no pool global isso descartava
        #    também o que o visualizador e a prévia tivessem pendente.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, (os.cpu_count() or 4) // 2))
        self._sig = _Signaller()
        self._sig.ready.connect(self._on_ready)
        self._sig.failed.connect(self._on_failed)
        self._inflight: set[int] = set()
        self._failed: set[int] = set()

    def get_or_request(self, asset_id: int, src: Path, content_hash: str,
                       priority: int = 1) -> Path | None:
        """Caminho da thumb se já existe; senão agenda a geração e retorna None.

        priority 1 = célula visível na grid (fura a fila);
        priority 0 = pré-aquecimento em background do resto da biblioteca.
        """
        dest = thumb_path(self._thumbs_dir, content_hash)
        if dest.exists():
            return dest
        if asset_id in self._inflight or asset_id in self._failed:
            return None
        self._inflight.add(asset_id)
        self._pool.start(_ThumbJob(self._sig, asset_id, src, dest), priority)
        return None

    def warmup(self, items: list[tuple[int, Path, str]]) -> int:
        """Agenda em prioridade baixa tudo que ainda não tem thumb.

        `items` = (asset_id, caminho absoluto, content_hash). Retorna quantos
        jobs foram agendados. A UI continua na frente da fila.
        """
        # Lista a pasta de miniaturas UMA vez em vez de perguntar ao disco
        # por item (Fatia 88). Na biblioteca real do Rafael o pré-aquecimento
        # recebe ~127 mil itens e agenda 726 — ou seja, 99,4% das chamadas
        # eram só pra confirmar que a miniatura já existia. Um `listdir` de
        # 46 mil nomes custa uma fração de 127 mil `exists()`.
        #
        # A pasta é PLANA (`thumb_path` = um arquivo por content_hash), então
        # comparar nomes num set é equivalente a perguntar ao disco.
        try:
            existentes = {p.name for p in self._thumbs_dir.iterdir()}
        except OSError:
            # Pasta ainda não existe (primeira execução) ou ilegível: cai no
            # caminho antigo, que pergunta ao disco item a item.
            log.warning("Não consegui listar %s — pré-aquecimento item a item.",
                        self._thumbs_dir, exc_info=True)
            existentes = None

        scheduled = 0
        for asset_id, src, content_hash in items:
            if existentes is None:
                if self.get_or_request(asset_id, src, content_hash, priority=0) is None \
                        and asset_id in self._inflight:
                    scheduled += 1
                continue

            # Monta só o NOME, sem criar um `Path` — são 127 mil itens, e
            # 99% deles só passam pelo teste de "já existe". O `Path` sai
            # depois, para as poucas centenas que de fato vão gerar.
            if thumb_name(content_hash) in existentes:
                continue
            if asset_id in self._inflight or asset_id in self._failed:
                continue
            self._inflight.add(asset_id)
            self._pool.start(
                _ThumbJob(self._sig, asset_id, src,
                          thumb_path(self._thumbs_dir, content_hash)), 0)
            scheduled += 1

        if scheduled:
            log.info("Pré-aquecimento: %d thumbnails agendadas em background.", scheduled)
        return scheduled

    def _on_ready(self, asset_id: int, path: str) -> None:
        self._inflight.discard(asset_id)
        self.ready.emit(asset_id, path)

    def _on_failed(self, asset_id: int) -> None:
        self._inflight.discard(asset_id)
        self._failed.add(asset_id)  # não tenta de novo nesta sessão

    def shutdown(self, timeout_ms: int = 3000) -> None:
        self._pool.clear()  # descarta jobs ainda não iniciados
        if not self._pool.waitForDone(timeout_ms):
            log.error("Pool de thumbnails não terminou em %dms.", timeout_ms)
