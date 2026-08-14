"""Estado de tela sobrevive a fechar e reabrir o app (Fatia 54).

Antes desta fatia nada de UI persistia: painel escondido, tag expandida,
pasta atual, filtros ativos e tamanho do slider sempre voltavam ao padrão
hardcoded a cada abertura — `closeEvent` só derrubava workers.
"""

import pytest
from PIL import Image
from PySide6.QtWidgets import QTreeWidgetItemIterator

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui import asset_grid
from assetdeck.ui.main_window import MainWindow


@pytest.fixture
def biblioteca(tmp_path, monkeypatch):
    """Só monta a biblioteca mínima e isola os diretórios — não abre
    janela nenhuma, porque este arquivo precisa abrir e fechar mais de
    uma (é o próprio ponto do teste)."""
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))
    config.ensure_dirs()
    cfg = config.load_config()
    cfg["bridge_port"] = 0  # evita colidir com o AssetDeck de verdade aberto
    config.save_config(cfg)

    root = tmp_path / "lib"
    root.mkdir()
    Image.new("RGB", (32, 32)).save(root / "textura.jpg")
    (root / "modelo.blend").write_bytes(b"blend" * 30)
    conn = connect(config.db_path())
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    conn.close()
    return root


def _abrir(root) -> MainWindow:
    conn = connect(config.db_path())
    return MainWindow(conn, str(root), config.db_path(), config.thumbs_dir())


def _item_por_nome(tree, nome):
    it = QTreeWidgetItemIterator(tree)
    while it.value():
        item = it.value()
        if item.text(0) == nome:
            return item
        it += 1
    return None


def test_sem_ui_state_salvo_abre_com_padroes(biblioteca, qapp):
    """config.json sem `ui_state` (ou `{}`) não pode quebrar nada — é o
    caso de quem nunca fechou o app depois desta fatia."""
    w = _abrir(biblioteca)
    w.show()
    qapp.processEvents()
    assert w.size_slider.value() == asset_grid.DEFAULT_ICON
    assert w.details.isVisible()
    w.close()


def test_fechar_e_reabrir_restaura_painel_oculto(biblioteca, qapp):
    w1 = _abrir(biblioteca)
    w1.show()
    qapp.processEvents()
    widget_tags = next(w for w, r in w1._panel_toggles if r == "Tags")
    acao_tags = next(
        acao for (_w, r), acao in zip(w1._panel_toggles, w1._window_menu_actions)
        if r == "Tags"
    )
    acao_tags.setChecked(False)
    assert not widget_tags.isVisible()
    w1.close()  # dispara closeEvent -> _save_ui_state()

    w2 = _abrir(biblioteca)
    w2.show()
    qapp.processEvents()
    widget_tags2 = next(w for w, r in w2._panel_toggles if r == "Tags")
    assert not widget_tags2.isVisible()
    w2.close()


def test_fechar_e_reabrir_restaura_tamanho_do_slider(biblioteca, qapp):
    w1 = _abrir(biblioteca)
    w1.size_slider.setValue(200)
    w1.close()

    w2 = _abrir(biblioteca)
    assert w2.size_slider.value() == 200
    w2.close()


def test_fechar_e_reabrir_restaura_tag_recolhida(biblioteca, qapp):
    """Uma tag com filho abre expandida na primeira carga (comportamento
    de sempre). Recolher, fechar e reabrir tem de manter recolhida —
    senão a fatia não fez nada além do padrão que já existia."""
    conn = connect(config.db_path())
    pai_id = tags_repo.create(conn, "Materiais")
    tags_repo.create(conn, "Madeira", parent_id=pai_id)
    conn.close()

    w1 = _abrir(biblioteca)
    item = _item_por_nome(w1.tags, "Materiais")
    assert item is not None
    assert item.isExpanded()  # primeira carga sempre abre quem tem filho
    item.setExpanded(False)
    w1.close()

    w2 = _abrir(biblioteca)
    item2 = _item_por_nome(w2.tags, "Materiais")
    assert item2 is not None
    assert not item2.isExpanded()
    w2.close()


def test_restaurar_layout_nao_e_afetado_pelo_estado_salvo(biblioteca, qapp):
    """`_restaurar_layout()` continua voltando aos tamanhos hardcoded,
    mesmo com um `ui_state` salvo diferente — é uma ação explícita,
    separada de 'lembrar entre sessões' (decisão do plano da Fatia 54)."""
    w1 = _abrir(biblioteca)
    w1.show()
    qapp.processEvents()
    w1._left_splitter.setSizes([10, 10, 10, 10])
    w1.close()

    w2 = _abrir(biblioteca)
    w2.show()
    qapp.processEvents()
    w2._restaurar_layout()
    assert w2._left_splitter.sizes() != [10, 10, 10, 10]
    w2.close()
