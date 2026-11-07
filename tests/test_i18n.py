"""Testes de internacionalizacao (i18n).

Verifica carregamento do QTranslator, resolucao de strings em ingles,
mecanismo de fallback para pt-BR e integridade do arquivo assetdeck_en.ts.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from PySide6.QtCore import QCoreApplication
import pytest

from assetdeck import config, i18n
from assetdeck.ui.preferences_dialog import PreferencesDialog


def test_translator_loads():
    """O translator de ingles deve carregar um QTranslator valido e nao-vazio."""
    trans = i18n.load_translator("en")
    assert trans is not None
    assert not trans.isEmpty()

    # pt_BR e a lingua-fonte; nao requer arquivo .qm
    assert i18n.load_translator("pt_BR") is None
    assert i18n.load_translator("idioma_inexistente") is None


def test_english_string_resolves(qapp):
    """Com o translator instalado, strings devem ser resolvidas para o ingles."""
    installed = i18n.install_translator(qapp, "en")
    assert installed is not None

    res1 = QCoreApplication.translate("PreferencesDialog", "Cena do render")
    assert res1 == "Render scene"

    res2 = QCoreApplication.translate("SettingsWindow", "Configurações")
    assert res2 == "Settings"

    res3 = QCoreApplication.translate("MainWindow", "Buscar assets")
    assert res3 == "Search assets"

    # Substituicao de marcadores com .arg()
    res4 = QCoreApplication.translate("ScanStats", "%1 novos").arg(42)
    assert res4 == "42 new"

    res5 = QCoreApplication.translate(
        "MainWindow", "Tag '%1' adicionada em %2 assets"
    ).arg("wood", 3)
    assert res5 == "Tag 'wood' added to 3 assets"


def test_fallback_works(qapp):
    """Ao desinstalar ou usar pt_BR, strings voltam para a fonte pt-BR."""
    i18n.install_translator(qapp, "pt_BR")

    res1 = QCoreApplication.translate("PreferencesDialog", "Cena do render")
    assert res1 == "Cena do render"

    res2 = QCoreApplication.translate("MainWindow", "Buscar assets")
    assert res2 == "Buscar assets"

    # Contexto ou string nao traduzida sob ingles deve retornar a string original
    i18n.install_translator(qapp, "en")
    res3 = QCoreApplication.translate("UnknownContext", "Texto desconhecido")
    assert res3 == "Texto desconhecido"

    # Restaura pt_BR para nao afetar outros testes
    i18n.install_translator(qapp, "pt_BR")


def test_no_unfinished_entries_in_en_ts():
    """O arquivo translations/assetdeck_en.ts nao deve conter entradas pendentes ou vazias."""
    ts_path = Path(__file__).resolve().parent.parent / "translations" / "assetdeck_en.ts"
    assert ts_path.exists(), f"Arquivo nao encontrado: {ts_path}"

    tree = ET.parse(ts_path)
    root = tree.getroot()

    messages = root.findall(".//message")
    assert len(messages) > 0, "Nenhuma mensagem encontrada em assetdeck_en.ts"

    unfinished = []
    empty = []
    em_dashes = []
    placeholder_mismatches = []

    for msg in messages:
        src_elem = msg.find("source")
        trans_elem = msg.find("translation")

        src_text = src_elem.text if src_elem is not None else ""
        if trans_elem is None:
            unfinished.append((src_text, "missing translation tag"))
            continue

        if trans_elem.attrib.get("type") == "unfinished":
            unfinished.append((src_text, "type=unfinished"))

        tgt_text = trans_elem.text or ""
        if not tgt_text.strip():
            empty.append(src_text)

        # Regra de projeto: proibido travessao em-dash
        if "\u2014" in tgt_text:
            em_dashes.append((src_text, tgt_text))

        src_ph = set(re.findall(r"%\d+", src_text))
        tgt_ph = set(re.findall(r"%\d+", tgt_text))
        if src_ph != tgt_ph:
            placeholder_mismatches.append((src_text, tgt_text, src_ph, tgt_ph))

    assert not unfinished, f"Entradas unfinished em assetdeck_en.ts: {unfinished[:10]}"
    assert not empty, f"Entradas vazias em assetdeck_en.ts: {empty[:10]}"
    assert not em_dashes, f"Entradas com travessao em assetdeck_en.ts: {em_dashes[:10]}"
    assert not placeholder_mismatches, (
        f"Divergencia de placeholders em assetdeck_en.ts: {placeholder_mismatches[:10]}"
    )


def test_normalize_language():
    """Valida normalizacao de codigos de idioma."""
    assert i18n.normalize_language("en") == "en"
    assert i18n.normalize_language("en_US") == "en"
    assert i18n.normalize_language("en_GB") == "en"
    assert i18n.normalize_language("pt") == "pt_BR"
    assert i18n.normalize_language("pt_BR") == "pt_BR"
    assert i18n.normalize_language("pt-BR") == "pt_BR"
    assert i18n.normalize_language("pt_PT") == "pt_BR"
    assert i18n.normalize_language("") == ""


def test_get_effective_language(monkeypatch):
    """Valida precedencia: config > locale > fallback pt-BR."""
    # Config explicito valido
    assert i18n.get_effective_language({"language": "en"}) == "en"
    assert i18n.get_effective_language({"language": "pt_BR"}) == "pt_BR"

    # Config desconhecido cai no fallback
    monkeypatch.setattr(i18n, "get_system_language", lambda: "pt_BR")
    assert i18n.get_effective_language({"language": "es_ES"}) == "pt_BR"
    assert i18n.get_effective_language({"language": ""}) == "pt_BR"


def test_preferences_dialog_language_selector(qapp, tmp_path, monkeypatch):
    """Testa selecao e persistencia de idioma no PreferencesDialog."""
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    cfg = config.load_config()
    cfg["language"] = "pt_BR"
    config.save_config(cfg)

    dlg = PreferencesDialog()
    assert dlg.language_combo.currentData() == "pt_BR"

    # Muda para ingles e salva
    idx_en = dlg.language_combo.findData("en")
    assert idx_en >= 0
    dlg.language_combo.setCurrentIndex(idx_en)
    dlg._salvar()

    saved = config.load_config()
    assert saved.get("language") == "en"

    # Abre novamente e verifica que selecionou ingles
    dlg2 = PreferencesDialog()
    assert dlg2.language_combo.currentData() == "en"
