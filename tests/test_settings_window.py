"""Janela de configurações (Fatia 67, reorganizada na 80).

Os testes de ponte/backup/previews automáticos MORAVAM em
`test_preferences_dialog.py`: eram controles daquela janela. Na Fatia 80
eles viraram LINHAS aqui, aplicando na hora em vez de esperar um "OK" —
a janela é não-modal. Os testes vieram junto, verificando o mesmo
comportamento no lugar novo.
"""

import pytest
from PIL import Image

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.main_window import MainWindow


@pytest.fixture
def janela(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))
    config.ensure_dirs()
    cfg = config.load_config()
    cfg["bridge_port"] = 0  # o SO escolhe uma porta livre (ver test_main_window)
    config.save_config(cfg)

    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "textura.jpg")

    conn = connect(config.db_path())
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    w = MainWindow(conn, str(root), config.db_path(), config.thumbs_dir())
    yield w
    w.close()
    conn.close()


# ------------------------------------------------------- estrutura (F80) --

def test_as_seis_categorias_estao_na_ordem_aprovada(janela):
    """Mockup aprovado pelo Rafael: "Ferramentas" virou "Manutenção",
    "Geral" virou "Sistema", e "Painéis e filtros" se partiu em dois — são
    perguntas diferentes ("quais painéis aparecem" e "o que a grade
    mostra")."""
    sw = janela.settings_window
    nomes = [sw._lista.item(i).text() for i in range(sw._lista.count())]
    assert nomes == ["Manutenção", "Blender", "Aparência",
                     "Painéis", "Filtros", "Sistema"]


def test_nao_existe_mais_pagina_preferencias(janela):
    """Era uma página cujo ÚNICO conteúdo era um botão que abria outra
    janela — um degrau a mais sem ganho nenhum."""
    sw = janela.settings_window
    nomes = [sw._lista.item(i).text() for i in range(sw._lista.count())]
    assert "Preferências" not in nomes


def test_cada_categoria_tem_uma_pagina(janela):
    sw = janela.settings_window
    assert sw._paginas.count() == sw._lista.count()


def test_reduzir_movimento_salva_e_aplica_na_grade(janela):
    check = janela.reduce_motion_check
    delegate = janela.grid.itemDelegate()

    assert check.isChecked() is False
    assert delegate._reduced_motion is False
    check.setChecked(True)
    assert config.load_config()["reduce_motion"] is True
    assert delegate._reduced_motion is True

    check.setChecked(False)
    assert config.load_config()["reduce_motion"] is False
    assert delegate._reduced_motion is False


# ------------------------ opções que vieram da janela de Preferências --

def test_a_ponte_carrega_o_valor_do_config(janela):
    """A porta não entra aqui de propósito: o fixture usa 0 (o SO escolhe
    uma livre) e o spinbox tem mínimo 1024, então ele mostra 1024 — o que
    NÃO é bug, é o campo recusando um valor fora da faixa que ele aceita.
    Quem cobre a porta é o teste de gravação logo abaixo."""
    cfg = config.load_config()
    assert janela.settings_window.bridge_enabled.isChecked() is bool(
        cfg.get("bridge_enabled", True))


def test_mudar_a_ponte_grava_na_hora(janela):
    """A janela é NÃO-MODAL: não há "OK" pra confirmar, então cada controle
    aplica ao mudar. Antes isso dependia de fechar a janela de Preferências
    no botão certo."""
    sw = janela.settings_window
    sw.bridge_enabled.setChecked(False)
    sw.bridge_port.setValue(48000)

    novo = config.load_config()
    assert novo["bridge_enabled"] is False
    assert novo["bridge_port"] == 48000


def test_backups_gravam_na_hora(janela):
    janela.settings_window.backup_keep.setValue(30)
    assert config.load_config()["backup_keep"] == 30


def test_preview_automatico_desligado_por_padrao(janela):
    """Mexe em vários assets de uma vez — nasce desligado de propósito."""
    assert janela.settings_window.auto_match_previews.isChecked() is False


def test_ocultar_origem_so_habilita_com_o_toggle_ligado(janela):
    """Ocultar a origem de um casamento que não acontece não quer dizer
    nada — o segundo controle depende do primeiro."""
    sw = janela.settings_window
    assert sw.auto_match_hide_source.isEnabled() is False

    sw.auto_match_previews.setChecked(True)
    assert sw.auto_match_hide_source.isEnabled() is True

    sw.auto_match_previews.setChecked(False)
    assert sw.auto_match_hide_source.isEnabled() is False


def test_os_dois_toggles_de_preview_gravam(janela):
    sw = janela.settings_window
    sw.auto_match_previews.setChecked(True)
    sw.auto_match_hide_source.setChecked(True)

    novo = config.load_config()
    assert novo["auto_match_previews_by_name"] is True
    assert novo["auto_match_hide_source"] is True


def test_origem_do_preview_grava_o_valor_interno_nao_o_rotulo(janela):
    """O combo mostra "Sempre ocultar a origem"; o config guarda "always" —
    é esse valor que `_on_asset_preview_dropped` lê."""
    from assetdeck.ui.preferences_dialog import _ORIGEM_LABEL

    sw = janela.settings_window
    sw.hide_preview_source.setCurrentText(_ORIGEM_LABEL["always"])
    assert config.load_config()["hide_preview_source"] == "always"


# ---- varredura automática na abertura (Fatia 92) ----

def test_varredura_na_abertura_vem_desligada():
    """Rafael, 2026-08-19: "tira a varredura automática da abertura".

    O app varria a biblioteca inteira em TODA abertura — 102 mil assets,
    minutos de CPU sem ninguém ter pedido. O padrão passou a ser não
    varrer; quem manda é o botão "Reindexar".
    """
    from assetdeck.app import varrer_na_abertura

    assert varrer_na_abertura({}) is False


def test_varredura_na_abertura_pode_ser_religada():
    """Não é remoção, é chave: quem quiser a sincronia automática liga em
    Configurações › Manutenção e ela volta a valer."""
    from assetdeck.app import varrer_na_abertura

    assert varrer_na_abertura({"scan_on_startup": True}) is True


def test_o_interruptor_da_varredura_grava_no_config(janela):
    """O controle existe na janela e aplica na hora (a janela é não-modal,
    não tem OK/Cancelar)."""
    sw = janela.settings_window
    sw.scan_on_startup.setChecked(True)
    assert config.load_config().get("scan_on_startup") is True

    sw.scan_on_startup.setChecked(False)
    assert config.load_config().get("scan_on_startup") is False
