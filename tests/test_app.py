"""Ícone do app (Fatia F4 — executável no menu do Zorin)."""

from pathlib import Path

from assetdeck.app import _set_app_icon


def test_set_app_icon_carrega_o_icone_de_verdade(qapp):
    antes = qapp.windowIcon()
    _set_app_icon(qapp)
    try:
        assert not qapp.windowIcon().isNull()
    finally:
        qapp.setWindowIcon(antes)  # não vazar pro resto da suíte


def test_set_app_icon_nao_quebra_se_o_arquivo_sumir(qapp, monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)
    antes = qapp.windowIcon()
    try:
        _set_app_icon(qapp)  # não pode lançar exceção — só loga e segue
        assert qapp.windowIcon().isNull() or qapp.windowIcon() == antes
    finally:
        qapp.setWindowIcon(antes)
