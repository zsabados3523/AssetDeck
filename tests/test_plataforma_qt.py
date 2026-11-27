"""Escolha da plataforma Qt em sessão Wayland."""

import os

import pytest

from assetdeck import app


@pytest.mark.parametrize(("sistema", "env", "esperado"), [
    ("linux", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, "xcb;wayland"),
    ("linux", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0",
               "QT_QPA_PLATFORM": "wayland"}, "wayland"),
    ("linux", {"WAYLAND_DISPLAY": "wayland-0"}, None),  # sem XWayland
    ("linux", {"DISPLAY": ":0"}, None),
    ("win32", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, None),
])
def test_preferir_x11(monkeypatch, sistema, env, esperado):
    monkeypatch.setattr(app.sys, "platform", sistema)
    monkeypatch.setattr(os, "environ", dict(env))

    app._preferir_x11()

    assert os.environ.get("QT_QPA_PLATFORM") == esperado
