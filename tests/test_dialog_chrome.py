"""Todos os diálogos mantêm o cabeçalho e a faixa de ações compartilhados."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QLabel

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.ui.batch_rename_dialog import BatchRenameDialog
from assetdeck.ui.duplicates_dialog import DuplicatesDialog
from assetdeck.ui.missing_textures_dialog import MissingTexturesDialog
from assetdeck.ui.preferences_dialog import PreferencesDialog
from assetdeck.ui.property_defs_dialog import PropertyDefsDialog
from assetdeck.ui.relocate_dialog import RelocateDialog
from assetdeck.ui.tag_templates_dialog import TagTemplateDialog


@pytest.fixture
def conn_dialogos(tmp_path):
    conn = connect(tmp_path / "dialogs.db")
    apply_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()


def test_todos_os_dialogos_usam_cabecalho_e_faixa_de_acoes(
        qapp, tmp_path, monkeypatch, conn_dialogos):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))
    config.ensure_dirs()

    dialogos = [
        TagTemplateDialog(conn_dialogos),
        PreferencesDialog(),
        MissingTexturesDialog(Path("modelo.blend"), [], 0),
        RelocateDialog([]),
        PropertyDefsDialog(conn_dialogos),
        DuplicatesDialog([]),
        BatchRenameDialog(conn_dialogos, 1, []),
    ]
    try:
        for dialogo in dialogos:
            assert dialogo.findChild(QLabel, "dialogHeading") is not None
            acoes = dialogo.findChild(QDialogButtonBox, "dialogActions")
            assert acoes is not None
    finally:
        for dialogo in dialogos:
            dialogo.close()
