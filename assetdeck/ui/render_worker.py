"""Fila de renders de capa em background (um Blender por vez)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from assetdeck.blender.render import (
    models_for_render,
    models_without_cover,
    render_thumbnail,
)
from assetdeck.db.connection import connect
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo

log = logging.getLogger(__name__)


class RenderWorker(QObject):
    progress = Signal(int, int, str)   # feitos, total, nome atual
    finished = Signal(int, int)        # sucessos, falhas
    failed = Signal(str)

    def __init__(self, db_path: Path, library_root: Path, previews_dir: Path,
                 size: int = 512, asset_ids: list[int] | None = None,
                 overwrite_existing: bool = False) -> None:
        super().__init__()
        self._db_path = db_path
        self._library_root = library_root
        self._previews_dir = previews_dir
        self._size = size
        # Restringe a fila a um subconjunto (Fatia 101) — `None` é "todos os
        # modelos sem capa", igual sempre foi.
        self._asset_ids = asset_ids
        self._overwrite_existing = overwrite_existing
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    @Slot()
    def run(self) -> None:
        try:
            # Config FRESCO a cada rodada (não uma vez só no __init__): o
            # Rafael pode mudar a cor em Preferências e clicar em "Gerar
            # capas" de novo sem reiniciar o app — diferente de
            # bridge_port/bridge_enabled, que só valem depois de reabrir
            # (aquele já está com um servidor de pé; render é sob demanda).
            from assetdeck import config as _cfg
            from assetdeck.blender.render import hex_to_linear_rgb

            cfg = _cfg.load_config()
            bg_color = hex_to_linear_rgb(cfg.get("render_bg_color", "#959599"))
            bg_strength = float(cfg.get("render_bg_strength", 1.8))
            sun_energy = float(cfg.get("render_sun_energy", 3.0))

            conn = connect(self._db_path)
            try:
                lib_id = libraries_repo.get_or_create(conn, self._library_root)
                if self._overwrite_existing:
                    jobs = models_for_render(
                        conn, lib_id, self._library_root,
                        asset_ids=self._asset_ids, overwrite_existing=True,
                    )
                    pendentes = [job[:3] for job in jobs]
                    cobertos = sum(job[3] for job in jobs)
                    log.info("Render de capas: %d modelos na fila, %d com capa atual.",
                             len(pendentes), cobertos)
                else:
                    pendentes = models_without_cover(
                        conn, lib_id, self._library_root, asset_ids=self._asset_ids)
                total = len(pendentes)
                if not total:
                    self.finished.emit(0, 0)
                    return
                log.info("Render de capas: %d modelos na fila.", total)

                ok = falhas = 0
                for i, (asset_id, nome, caminho) in enumerate(pendentes, start=1):
                    if self._stop.is_set():
                        log.info("Render interrompido a pedido (%d/%d).", i - 1, total)
                        break
                    self.progress.emit(i, total, nome)
                    destino = self._previews_dir / f"render_{asset_id}.png"
                    resultado = render_thumbnail(
                        Path(caminho), destino, self._size,
                        bg_color=bg_color, bg_strength=bg_strength, sun_energy=sun_energy,
                    )
                    if resultado.ok:
                        # Registra como preview 'blender' e vira a capa
                        previews_repo.add(conn, asset_id, destino,
                                          self._previews_dir, origin="blender")
                        destino.unlink(missing_ok=True)  # previews_repo já copiou
                        ok += 1
                    else:
                        falhas += 1
                self.finished.emit(ok, falhas)
            finally:
                conn.close()
        except Exception as exc:
            log.exception("Fila de render falhou")
            self.failed.emit(str(exc))


class RenderController(QObject):
    """Dono da QThread da fila de renders."""

    def __init__(self, db_path: Path, library_root: Path, previews_dir: Path,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._library_root = library_root
        self._previews_dir = previews_dir
        self._thread: QThread | None = None
        self._worker: RenderWorker | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, on_progress, on_finished, on_failed,
              asset_ids: list[int] | None = None,
              overwrite_existing: bool = False) -> None:
        if self.running:
            return
        self._thread = QThread()
        self._worker = RenderWorker(self._db_path, self._library_root,
                                    self._previews_dir, asset_ids=asset_ids,
                                    overwrite_existing=overwrite_existing)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(on_progress)
        self._worker.finished.connect(on_finished)
        self._worker.failed.connect(on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def shutdown(self, timeout_ms: int = 5000) -> None:
        if self._worker:
            self._worker.request_stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(timeout_ms):
                log.error("Thread de render não terminou em %dms.", timeout_ms)
