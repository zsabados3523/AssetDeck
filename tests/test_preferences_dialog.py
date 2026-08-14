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


# ---- cena de render (Fatia 38) ----

def test_cena_de_render_carrega_do_config(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    cfg = config.load_config()
    cfg["render_bg_color"] = "#112233"
    cfg["render_bg_strength"] = 4.5
    cfg["render_sun_energy"] = 7.5
    config.save_config(cfg)

    dlg = PreferencesDialog()

    assert dlg._render_bg_color == "#112233"
    assert dlg.render_bg_strength.value() == 4.5
    assert dlg.render_sun_energy.value() == 7.5


def test_escolher_cor_do_fundo_atualiza_o_estado(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    _isolar(tmp_path, monkeypatch)
    config.load_config()
    dlg = PreferencesDialog()

    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#ff8800")))
    dlg._escolher_cor_fundo()

    assert dlg._render_bg_color == "#ff8800"


def test_cancelar_o_seletor_de_cor_nao_muda_nada(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    _isolar(tmp_path, monkeypatch)
    config.load_config()
    dlg = PreferencesDialog()
    original = dlg._render_bg_color

    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor()))  # inválida = cancelou
    dlg._escolher_cor_fundo()

    assert dlg._render_bg_color == original


def test_salvar_grava_a_cena_de_render(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    config.load_config()

    dlg = PreferencesDialog()
    dlg._render_bg_color = "#abcdef"
    dlg.render_bg_strength.setValue(2.5)
    dlg.render_sun_energy.setValue(6.0)
    dlg._salvar()

    novo = config.load_config()
    assert novo["render_bg_color"] == "#abcdef"
    assert novo["render_bg_strength"] == 2.5
    assert novo["render_sun_energy"] == 6.0


# ---- preview automático por nome igual (Fatia 57) ----

def test_preview_automatico_desligado_por_padrao(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    config.load_config()

    dlg = PreferencesDialog()

    assert dlg.auto_match_previews.isChecked() is False
    assert dlg.auto_match_hide_source.isEnabled() is False  # sem sentido sem o pai ligado


def test_ocultar_origem_so_habilita_com_o_toggle_ligado(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    config.load_config()
    dlg = PreferencesDialog()

    dlg.auto_match_previews.setChecked(True)
    assert dlg.auto_match_hide_source.isEnabled() is True

    dlg.auto_match_previews.setChecked(False)
    assert dlg.auto_match_hide_source.isEnabled() is False


def test_salvar_grava_os_dois_toggles(qapp, tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    config.load_config()

    dlg = PreferencesDialog()
    dlg.auto_match_previews.setChecked(True)
    dlg.auto_match_hide_source.setChecked(True)
    dlg._salvar()

    novo = config.load_config()
    assert novo["auto_match_previews_by_name"] is True
    assert novo["auto_match_hide_source"] is True
