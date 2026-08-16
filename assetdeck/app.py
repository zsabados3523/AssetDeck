"""Bootstrap do app: config → logging → banco → backup → janela."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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


# Basename de install_desktop_entry.py's DEST (assetdeck.desktop, sem a
# extensão) — é o "nome" que o GNOME usa pra casar a janela aberta com o
# ícone fixado no dock. Tem que bater com os dois lugares.
DESKTOP_FILE_ID = "assetdeck"


def _set_app_icon(app) -> None:
    """Identidade da janela pro sistema: ícone (barra de tarefas, alt-tab) E
    o nome que o GNOME usa pra achar o `.desktop` correspondente.

    Bug relatado pelo Rafael: fixar o app no dock e abrir mostrava OUTRO
    ícone (o de engrenagem genérico) em vez do do AssetDeck — o dock abria
    uma instância nova, sem reconhecer que era o app fixado. Causa: sem
    `setDesktopFileName`, o Qt identifica a janela pelo nome do PROCESSO
    (`python`, já que o app roda via `.venv/bin/python -m assetdeck`, não
    instalado via pip) — o GNOME tenta casar isso com `assetdeck.desktop`
    e não bate. `setDesktopFileName` resolve pela raiz: manda o Qt anunciar
    a janela com o MESMO nome do `.desktop` (WM_CLASS no X11).
    """
    from PySide6.QtGui import QIcon

    app.setDesktopFileName(DESKTOP_FILE_ID)

    caminho = Path(__file__).parent / "ui" / "icons" / "app-icon.png"
    if not caminho.exists():
        log.warning("Ícone do app não encontrado em %s", caminho)
        return
    app.setWindowIcon(QIcon(str(caminho)))


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
    _set_app_icon(app)
    win = ThemeGallery()
    win.show()
    log.info("Vitrine do tema aberta (--theme-preview).")
    _schedule_screenshot(app, win, args)
    return app.exec()


def _confirmar_biblioteca(conn, cfg: dict, silencioso: bool) -> str:
    """Confere se a biblioteca está onde o config diz — e resolve se não estiver.

    Bug real (2026-08-09): o SSD do Rafael montou em `/mnt/<uuid>` em vez do
    `/media/rafael/SSD` gravado no config. O app abria como se nada fosse (as
    miniaturas vêm do cache), mas qualquer operação que precisasse LER o
    arquivo original falhava só no log — arrastar imagem para virar preview
    de um modelo "não fazia nada" na tela. Agora o app fala na cara, na
    abertura, antes de o usuário perder tempo.

    Devolve o caminho da biblioteca a usar nesta sessão.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from assetdeck import library_root

    configurado = Path(cfg["library_root"])
    res = library_root.resolve(configurado)

    if res.ok:
        return str(res.found)

    # --screenshot roda sem ninguém na frente da tela: um diálogo modal
    # travaria a captura para sempre. Loga e segue.
    if silencioso:
        log.error("Biblioteca fora do lugar (%s) — seguindo assim mesmo (modo silencioso).",
                  configurado)
        return str(configurado)

    if res.moved:
        escolha = QMessageBox.question(
            None, "A biblioteca mudou de lugar",
            f"O AssetDeck procurava a biblioteca em:\n{configurado}\n\n"
            f"Ela não está lá, mas eu encontrei em:\n{res.found}\n\n"
            "Isso costuma acontecer quando o disco externo é montado num "
            "caminho diferente do da última vez.\n\n"
            "Quer que eu passe a usar o caminho novo? "
            "(nada é movido nem renomeado no disco)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if escolha != QMessageBox.StandardButton.Yes:
            log.warning("Rafael recusou repontar a biblioteca para %s", res.found)
            return str(configurado)
        novo = res.found
    else:
        QMessageBox.warning(
            None, "Biblioteca não encontrada",
            f"O AssetDeck não achou a biblioteca em:\n{configurado}\n\n"
            "Procurei também nos discos montados e não estava em nenhum.\n\n"
            "Se o disco externo estiver desconectado, feche o app, conecte "
            "e abra de novo. Se ela mudou de pasta, escolha a nova pasta na "
            "próxima tela (ou cancele para abrir mesmo assim — a grade "
            "aparece, mas nada que leia os arquivos vai funcionar).",
        )
        escolhido = QFileDialog.getExistingDirectory(
            None, "Onde está a biblioteca?", str(Path.home()),
        )
        if not escolhido:
            log.warning("Rafael cancelou a escolha da biblioteca — abrindo com %s",
                        configurado)
            return str(configurado)
        novo = Path(escolhido)

    linhas = library_root.repoint(conn, configurado, novo)
    cfg["library_root"] = str(novo)
    config.save_config(cfg)
    log.info("Biblioteca repontada para %s (%d linha(s) no banco)", novo, linhas)
    return str(novo)


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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from assetdeck.ui.hdri_viewer import ensure_gl_format
    from assetdeck.ui.main_window import MainWindow

    # Tem de vir ANTES do QApplication: o visualizador de HDRI (Fatia 34)
    # usa shaders #version 330, que não compilam num contexto de
    # compatibilidade antigo — e o formato padrão é imutável depois.
    ensure_gl_format()

    # Também tem de vir ANTES do QApplication. Candidato pro "piscar" do
    # visualizador de HDRI (Fatia 65, nunca resolvido de verdade — e agora
    # o visualizador de modelo 3D, Fatia 71, tem o mesmo sintoma): sem
    # isso, CADA janela de topo paga sozinha o custo de negociar sua
    # própria superfície OpenGL a primeira vez que um QOpenGLWidget
    # aparece nela — é essa negociação que o Rafael vê como "pisca".
    # AA_ShareOpenGLContexts é a flag padrão do Qt pra isso: monta UM
    # contexto GL compartilhado cedo, pras janelas de topo seguintes
    # (HdriViewer, ModelViewer) reusarem em vez de negociar do zero.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv[:1])

    from assetdeck.ui import theme

    theme.apply_theme(app, theme.Variant(mode=cfg.get("theme_mode", "claro")))
    _set_app_icon(app)

    # Depois do QApplication (precisa dele para abrir diálogo) e ANTES da
    # janela — a MainWindow recebe a raiz já conferida.
    raiz = _confirmar_biblioteca(conn, cfg, silencioso=bool(args.screenshot))

    win = MainWindow(conn=conn, library_root=raiz,
                     db_path=config.db_path(), thumbs_dir=config.thumbs_dir())
    win.show()
    win.start_scan()  # indexação em background a cada abertura (idempotente)

    _schedule_screenshot(app, win, args)

    return app.exec()
