"""Bootstrap do app: config → logging → banco → backup → janela."""

from __future__ import annotations

import argparse
import logging
import sys

from assetdeck import __version__, config
from assetdeck.backup.rotate import daily_backup
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.logging_setup import setup_logging

log = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="assetdeck", description="AssetDeck — DAM local")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="salva um screenshot da janela em PATH e sai")
    parser.add_argument("--screenshot-delay", type=int, default=400, metavar="MS",
                        help="espera MS milissegundos antes do screenshot (padrão: 400)")
    parser.add_argument("--theme-preview", action="store_true",
                        help="abre a vitrine do tema (F4) em vez da janela do app")
    parser.add_argument("--version", action="version", version=f"assetdeck {__version__}")
    return parser.parse_args(argv)


def _schedule_screenshot(app, win, args) -> None:
    """Agenda a captura da janela e o encerramento, se --screenshot foi pedido."""
    if not args.screenshot:
        return

    from PySide6.QtCore import QTimer

    def _grab() -> None:
        ok = win.grab().save(args.screenshot)
        if ok:
            log.info("Screenshot salvo em %s", args.screenshot)
        else:
            log.error("Não consegui salvar o screenshot em %s", args.screenshot)
        win.close()  # encerra a thread de varredura com segurança
        app.exit(0 if ok else 1)

    QTimer.singleShot(args.screenshot_delay, _grab)  # espera a janela desenhar


def _run_theme_preview(args) -> int:
    """Vitrine do tema (F4): não abre banco nem indexa — só desenha widgets."""
    import sys as _sys

    from PySide6.QtWidgets import QApplication

    from assetdeck.ui.theme_gallery import ThemeGallery

    app = QApplication(_sys.argv[:1])
    win = ThemeGallery()
    win.show()
    log.info("Vitrine do tema aberta (--theme-preview).")
    _schedule_screenshot(app, win, args)
    return app.exec()


def run(argv: list[str]) -> int:
    args = parse_args(argv)

    config.ensure_dirs()
    setup_logging(config.logs_dir())

    if args.theme_preview:
        return _run_theme_preview(args)

    cfg = config.load_config()
    log.info("AssetDeck %s iniciando — biblioteca: %s", __version__, cfg["library_root"])

    conn = connect(config.db_path())
    version = apply_migrations(conn)
    log.info("Banco na versão %d (%s)", version, config.db_path())

    created = daily_backup(config.db_path(), config.backups_dir(), keep=cfg["backup_keep"])
    if created is None:
        log.info("Backup de hoje já existia — nada a fazer.")

    # Import tardio: os testes de banco/backup/scanner rodam sem Qt carregado.
    from PySide6.QtWidgets import QApplication

    from assetdeck.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    win = MainWindow(conn=conn, library_root=cfg["library_root"],
                     db_path=config.db_path(), thumbs_dir=config.thumbs_dir())
    win.show()
    win.start_scan()  # indexação em background a cada abertura (idempotente)

    _schedule_screenshot(app, win, args)

    return app.exec()
