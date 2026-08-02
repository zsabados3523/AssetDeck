"""Duplo clique: HDRI abre o visualizador novo, o resto segue no popup
de sempre (Fatia 34).

Arquivo próprio porque precisa de uma biblioteca COM um .hdr de verdade —
o fixture `janela` de test_main_window.py é só .jpg + .blend, e outros
testes lá dependem dele ter exatamente 2 assets.
"""

import numpy as np
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

    import cv2  # já é dependência (thumbs/hdr.py)

    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "textura.jpg")
    # .hdr Radiance de verdade: céu claro em cima, chão escuro embaixo
    hdr = np.zeros((8, 16, 3), np.float32)
    hdr[:4] = (2.0, 1.5, 1.0)
    hdr[4:] = (0.1, 0.1, 0.1)
    assert cv2.imwrite(str(root / "ceu.hdr"), hdr)

    conn = connect(config.db_path())
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    w = MainWindow(conn, str(root), config.db_path(), config.thumbs_dir())
    yield w
    w.close()
    conn.close()


@pytest.fixture
def espiao(janela, monkeypatch):
    """Registra qual janela cada duplo clique abriria. O visualizador é
    dublado: instanciá-lo exige contexto OpenGL, que não existe no modo
    offscreen do pytest."""
    abertos = []

    class _ViewerFalso:
        def show_for(self, path):
            abertos.append(("hdri", path.name))

    monkeypatch.setattr(janela, "_hdri_viewer", lambda: _ViewerFalso())
    monkeypatch.setattr(janela.preview_popup, "show_for",
                        lambda row, *a, **k: abertos.append(("popup", row["name"])))
    return abertos


def _abrir(janela, nome):
    for linha in range(janela.model.rowCount()):
        if janela.model.row_at(janela.model.index(linha))["name"] == nome:
            janela._open_preview(janela.model.index(linha))
            return
    raise AssertionError(f"{nome} não está na grade")


def test_hdri_abre_o_visualizador(janela, espiao):
    _abrir(janela, "ceu")
    assert espiao == [("hdri", "ceu.hdr")]


def test_imagem_comum_continua_no_popup(janela, espiao):
    _abrir(janela, "textura")
    assert espiao == [("popup", "textura")]


def test_o_visualizador_so_e_criado_quando_ha_hdri(janela):
    """Quem nunca abre um HDRI não paga o custo do contexto OpenGL."""
    assert getattr(janela, "_hdri_win", None) is None
