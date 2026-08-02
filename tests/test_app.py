"""Ícone e identidade do app (Fatia F4 — executável no menu do Zorin)."""

from pathlib import Path

from assetdeck.app import DESKTOP_FILE_ID, _set_app_icon


def test_set_app_icon_carrega_o_icone_de_verdade(qapp):
    antes = qapp.windowIcon()
    _set_app_icon(qapp)
    try:
        assert not qapp.windowIcon().isNull()
    finally:
        qapp.setWindowIcon(antes)  # não vazar pro resto da suíte


def test_set_app_icon_avisa_o_desktop_file_name(qapp):
    """Bug relatado pelo Rafael: fixar no dock e abrir mostrava OUTRO
    ícone (engrenagem genérica) em vez do do AssetDeck — o GNOME não
    reconhecia a janela como pertencente ao .desktop fixado, porque sem
    isto o Qt identifica a janela pelo nome do PROCESSO (`python`), não
    do app. `DESKTOP_FILE_ID` tem que bater com o basename do arquivo que
    install_desktop_entry.py escreve (assetdeck.desktop)."""
    antes = qapp.desktopFileName()
    _set_app_icon(qapp)
    try:
        assert qapp.desktopFileName() == DESKTOP_FILE_ID == "assetdeck"
    finally:
        qapp.setDesktopFileName(antes)


def test_set_app_icon_nao_quebra_se_o_arquivo_sumir(qapp, monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    antes = qapp.windowIcon().cacheKey()  # QIcon não tem __eq__ útil; cacheKey sim
    _set_app_icon(qapp)  # não pode lançar exceção — só loga e segue
    assert qapp.windowIcon().cacheKey() == antes  # ícone não mudou
