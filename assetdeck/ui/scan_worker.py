"""Ponte entre o scanner (lógica pura) e a UI Qt.

O worker roda numa QThread própria com a SUA conexão SQLite (conexões sqlite3
não podem cruzar threads). O modo WAL deixa a UI ler enquanto ele escreve.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from assetdeck.db.connection import connect
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import ScanStats, scan_library

log = logging.getLogger(__name__)


class ScanWorker(QObject):
    """Executa uma varredura completa e emite sinais de progresso."""

    progress = Signal(int, int, int)   # contagem/fase, total ou marcador, assets ativos
    finished = Signal(object)          # ScanStats
    failed = Signal(str)               # mensagem legível

    def __init__(self, db_path: Path, library_root: Path) -> None:
        super().__init__()
        self._db_path = db_path
        self._library_root = library_root
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    @Slot()
    def run(self) -> None:
        try:
            conn = connect(self._db_path)
            try:
                library_id = libraries_repo.get_or_create(conn, self._library_root)
                active_at_start = assets_repo.count_active(conn, library_id=library_id)

                def on_progress(done: int, total: int, _stats: ScanStats) -> None:
                    # A contagem muda apenas quando entram assets novos. Uma
                    # única consulta no início evita COUNT(*) a cada 10 itens.
                    self.progress.emit(done, total, active_at_start + _stats.added)

                stats = scan_library(
                    conn, library_id, self._library_root,
                    progress=on_progress,
                    should_stop=self._stop.is_set,
                )
                if not stats.aborted:
                    # Pós-processamento, tudo nesta thread (a UI não trava):
                    # agrupar sets PBR → marcar dependências → capas de pack
                    # → capas por nome igual (Fatia 57, opt-in)
                    from assetdeck import config
                    from assetdeck.indexer.dependencies import (
                        attach_pack_previews,
                        attach_stem_match_previews,
                        detect,
                    )
                    from assetdeck.indexer.grouper import apply_grouping

                    gstats = apply_grouping(conn, library_id)
                    stats.grouped_sets = gstats.sets_created
                    detect(conn, library_id)
                    attach_pack_previews(conn, library_id, self._library_root,
                                         config.previews_dir())
                    cfg = config.load_config()
                    if cfg.get("auto_match_previews_by_name"):
                        attach_stem_match_previews(
                            conn, library_id, self._library_root,
                            config.previews_dir(),
                            hide_source=bool(cfg.get("auto_match_hide_source")),
                        )
                self.finished.emit(stats)
            finally:
                conn.close()
        except Exception as exc:
            log.exception("Varredura falhou")
            self.failed.emit(str(exc))


class ScanController(QObject):
    """Dono da QThread: cria, conecta e desmonta com segurança."""

    def __init__(self, db_path: Path, library_root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._library_root = library_root
        self._thread: QThread | None = None
        self._worker: ScanWorker | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, on_progress, on_finished, on_failed) -> None:
        if self.running:
            log.info("Varredura já em andamento — pedido ignorado.")
            return
        self._thread = QThread()
        self._worker = ScanWorker(self._db_path, self._library_root)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(on_progress)
        self._worker.finished.connect(on_finished)
        self._worker.failed.connect(on_failed)
        # Desmonte: qualquer fim de varredura encerra a thread
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)

        self._thread.start()
        log.info("Varredura iniciada em background.")

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Pede parada e espera a thread morrer (chamado ao fechar a janela)."""
        if self._worker:
            self._worker.request_stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(timeout_ms):
                log.error("Thread de varredura não terminou em %dms.", timeout_ms)
