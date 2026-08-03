"""Fatia 36: diálogo de preferências — só regrava config.json, sem UI antes."""

from assetdeck import config
from assetdeck.ui.preferences_dialog import PreferencesDialog


def _isolar(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))


def test_carrega_valores_atuais_do_config(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    cfg = config.load_config()
    cfg["bridge_port"] = 50000
    cfg["hide_preview_source"] = "always"
    config.save_config(cfg)

    dlg = PreferencesDialog()
    assert dlg.bridge_port.value() == 50000
    assert dlg.hide_preview_source.currentText() == "Sempre ocultar a origem"


def test_salvar_regrava_o_config_json(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    config.load_config()  # cria com padrões

    dlg = PreferencesDialog()
    dlg.bridge_enabled.setChecked(False)
    dlg.bridge_port.setValue(48000)
    dlg.hide_preview_source.setCurrentText("Nunca ocultar a origem")
    dlg.backup_keep.setValue(30)
    dlg._salvar()

    novo = config.load_config()
    assert novo["bridge_enabled"] is False
    assert novo["bridge_port"] == 48000
    assert novo["hide_preview_source"] == "never"
    assert novo["backup_keep"] == 30
