"""Testes para o estado de primeira execução sem biblioteca configurada.

Garante que:
1. O config padrão inicial tem library_root vazio ("").
2. library_root.resolve() e scanner nunca resolvem nem varrem o cwd.
3. O app e MainWindow abrem normalmente em estado vazio com botão de escolha.
"""

from pathlib import Path
import pytest
from PySide6.QtWidgets import QMessageBox

from assetdeck import config, library_root
from assetdeck.app import _confirmar_biblioteca
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.main_window import MainWindow
from assetdeck.ui.scan_worker import ScanController


def test_config_nova_sem_library_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    cfg = config.load_config()
    assert cfg["library_root"] == ""
    assert config.DEFAULTS["library_root"] == ""


def test_library_root_resolve_vazio_nao_resolve_para_cwd():
    for vazio in ("", "   ", Path(""), Path(".")):
        res = library_root.resolve(vazio)
        assert not res.ok
        assert res.missing
        assert res.found is None
        assert not res.moved


def test_scan_library_recusa_raiz_vazia_e_nao_toca_no_cwd(tmp_path):
    conn = connect(tmp_path / "test.db")
    apply_migrations(conn)

    for alvo in (Path(""), Path("."), None):
        with pytest.raises(RuntimeError) as exc_info:
            scan_library(conn, 1, alvo)
        assert "não foi configurada" in str(exc_info.value) or "não existe" in str(exc_info.value)

    # Garante que nenhum arquivo do cwd foi adicionado ao banco
    assert assets_repo.count_active(conn) == 0
    conn.close()


def test_libraries_repo_recusa_raiz_vazia_ou_ponto(tmp_path):
    conn = connect(tmp_path / "test.db")
    apply_migrations(conn)

    for invalido in ("", ".", Path(""), Path(".")):
        with pytest.raises(ValueError):
            libraries_repo.get_or_create(conn, invalido)
    conn.close()


def test_scan_controller_recusa_raiz_vazia(tmp_path):
    falhas = []
    ctrl = ScanController(tmp_path / "db.sqlite", Path(""))
    ctrl.start(
        on_progress=lambda *_: None,
        on_finished=lambda *_: None,
        on_failed=lambda err: falhas.append(err),
    )
    assert len(falhas) == 1
    assert "Nenhuma pasta" in falhas[0]
    assert not ctrl.running


def test_confirmar_biblioteca_sem_library_root_retorna_vazio_sem_dialogo(tmp_path):
    conn = connect(tmp_path / "test.db")
    apply_migrations(conn)

    cfg = {"library_root": ""}
    # silencioso=False para garantir que não tenta abrir QMessageBox
    resultado = _confirmar_biblioteca(conn, cfg, silencioso=False)
    assert resultado == ""
    conn.close()


def test_main_window_abre_sem_biblioteca(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))
    config.ensure_dirs()

    cfg = config.load_config()
    cfg["bridge_port"] = 0
    cfg["library_root"] = ""
    config.save_config(cfg)

    conn = connect(config.db_path())
    apply_migrations(conn)

    win = MainWindow(conn, "", config.db_path(), config.thumbs_dir())
    win.show()

    try:
        assert not win._has_library
        assert win._library_root is None
        assert win._library_id is None

        # Empty state visível e grid oculta
        assert win.empty_state_widget.isVisible()
        assert not win.grid.isVisible()
        assert not win.rescan_btn.isEnabled()

        # Seletor exibe "Sem biblioteca"
        assert win.library_switcher.text() == "Sem biblioteca"

        # start_scan não faz nada e não varre cwd
        win.start_scan()
        assert not win._scan.running
        assert assets_repo.count_active(conn) == 0

        # Contagens de rodapé e escopo
        assert win.refresh_count() == 0
        assert win.footer_count.text() == "0 assets"
        assert win.list_count.text() == "0 assets"
        assert win.footer_size.text() == "0 B"
    finally:
        win.close()
        conn.close()
