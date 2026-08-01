"""Teste de fumaça da janela principal.

Existe porque um NameError em _setup_bridge impediu o app de abrir e nenhum
teste pegou: nada instanciava a MainWindow.
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

    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "textura.jpg")
    (root / "modelo.blend").write_bytes(b"blend" * 30)

    conn = connect(config.db_path())
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    w = MainWindow(conn, str(root), config.db_path(), config.thumbs_dir())
    yield w
    w.close()
    conn.close()


def test_janela_abre_com_todos_os_paineis(janela):
    assert janela.model.rowCount() == 2
    for atributo in ("grid", "details", "folders", "tags", "collections",
                     "smart_collections", "type_filter",
                     "search_box", "deps_check", "hidden_check", "group_check"):
        assert getattr(janela, atributo) is not None


def test_smart_collection_salva_e_aplica_filtros(janela):
    """Ciclo completo pela janela real: marcar filtros, salvar, mudar os
    filtros para outra coisa e aplicar a coleção inteligente salva."""
    janela.type_filter.set_selected(["texture"])
    janela._apply_filters()
    assert janela.model.rowCount() == 1  # só a textura.jpg

    janela._on_save_smart_collection("Só texturas")

    janela.type_filter.set_selected(["model"])
    janela._apply_filters()
    assert janela.model.rowCount() == 1  # só o modelo.blend

    salva = janela.smart_collections.item(1)  # índice 0 é "(nenhuma aplicada)"
    assert salva.text() == "Só texturas"
    janela.smart_collections.setCurrentItem(salva)

    assert janela.type_filter.selected() == ["texture"]
    assert janela.model.rowCount() == 1
    assert janela.model.row_at(janela.model.index(0))["name"] == "textura"


def test_ponte_e_render_ficam_prontos(janela):
    """Cobre o NameError que derrubava a abertura do app."""
    assert janela._bridge is not None
    assert janela._bridge.listening
    assert janela._render is not None
    assert janela._render.running is False


def test_menu_blender_tem_as_acoes(janela):
    menus = [m.title() for m in janela.menuBar().findChildren(type(janela.menuBar().addMenu("x")))]
    assert any("Blender" in t for t in menus)
    assert janela.render_action.isEnabled()
    assert janela.cancel_render_action.isEnabled() is False


def test_menu_biblioteca_tem_relocalizar(janela):
    menus = [m.title() for m in janela.menuBar().findChildren(type(janela.menuBar().addMenu("x")))]
    assert any("Biblioteca" in t for t in menus)
    assert janela.relocate_action.isEnabled()


def test_filtros_nao_quebram_a_grid(janela, qapp):
    janela.search_box.setText("textura")
    janela._apply_filters()
    assert janela.model.rowCount() == 1

    janela.search_box.setText("")
    janela.deps_check.setChecked(True)
    janela._apply_filters()
    assert janela.model.rowCount() == 2


def test_reload_grid_funciona_com_lista_vazia(janela):
    janela.search_box.setText("nao-existe-nada-assim")
    janela._apply_filters()
    assert janela.model.rowCount() == 0
    janela._reload_grid()  # não pode levantar
