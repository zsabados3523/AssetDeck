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
from assetdeck.ui.tag_dialogs import AliasDialog, QuickTagDialog, TagIconDialog
from assetdeck.db.repos import tags as tags_repo


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
    tag_id = tags_repo.create(conn_dialogos, "Acabamento")

    dialogos = [
        TagTemplateDialog(conn_dialogos),
        PreferencesDialog(),
        MissingTexturesDialog(Path("modelo.blend"), [], 0),
        RelocateDialog([]),
        PropertyDefsDialog(conn_dialogos),
        DuplicatesDialog([]),
        BatchRenameDialog(conn_dialogos, 1, []),
        QuickTagDialog(conn_dialogos, []),
        AliasDialog(conn_dialogos, tag_id),
        TagIconDialog(conn_dialogos, tag_id),
    ]
    try:
        for dialogo in dialogos:
            assert dialogo.findChild(QLabel, "dialogHeading") is not None
            acoes = dialogo.findChild(QDialogButtonBox, "dialogActions")
            assert acoes is not None
            assert acoes.objectName() == "dialogActions"
    finally:
        for dialogo in dialogos:
            dialogo.close()


def test_caixas_de_mensagem_têm_acoes_padronizadas_e_em_portugues(qapp):
    from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

    from assetdeck.ui.theme import _PopupCornerMask

    caixa = QMessageBox()
    caixa.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    _PopupCornerMask._prepare_dialog(caixa, QDialogButtonBox, QMessageBox)

    assert caixa.objectName() == "assetdeckMessageBox"
    assert caixa.button(QMessageBox.StandardButton.Yes).text() == "Sim"
    assert caixa.button(QMessageBox.StandardButton.No).text() == "Não"
