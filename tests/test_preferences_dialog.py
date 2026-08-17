"""Fatia 36: diálogo de preferências — só regrava config.json, sem UI antes."""

from assetdeck import config
from assetdeck.ui.preferences_dialog import PreferencesDialog


def _isolar(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))


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

