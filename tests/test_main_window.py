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


def test_breadcrumb_acompanha_a_pasta_selecionada(janela):
    """Fatia 28: o caminho acima da grade é a única pista visível de 'onde
    estou' depois de rolar — tem de mudar com a seleção na árvore.

    `_on_dir_selected` é o slot real conectado a `folders.dir_selected`
    (testado à parte, na FolderTree). Chamar direto evita depender de uma
    subpasta existir na biblioteca mínima do fixture `janela`.
    """
    assert janela.breadcrumb.text() == "BIBLIOTECA (TUDO)"

    janela._on_dir_selected("Modelos/Cadeiras")
    assert janela.breadcrumb.text() == "BIBLIOTECA › MODELOS › CADEIRAS"

    janela._on_dir_selected("")
    assert janela.breadcrumb.text() == "BIBLIOTECA (TUDO)"


def test_footer_mostra_contagem_e_atualiza_com_selecao(janela):
    """A contagem saiu da barra de filtros (eram 11 widgets na mesma linha)
    e virou permanente no rodapé (Fatia 28)."""
    assert "assets" in janela.footer_count.text()
    assert "selecionado" not in janela.footer_count.text()

    janela.grid.selectionModel().select(
        janela.model.index(0),
        janela.grid.selectionModel().SelectionFlag.Select,
    )
    janela.grid.selectionModel().select(
        janela.model.index(1),
        janela.grid.selectionModel().SelectionFlag.Select,
    )
    janela.refresh_count()
    assert "2 selecionados" in janela.footer_count.text()


def test_tema_pinta_a_janela_e_os_cards_ficam_arredondados(qapp, janela):
    """Regressão da Fatia 25: aplicar o QSS global e conferir na janela REAL
    (não numa sonda isolada) que o cartão da grade tem o canto arredondado —
    é onde o bug do viewport retangular vazando apareceria de verdade."""
    from assetdeck.ui import theme

    antes = (qapp.styleSheet(), qapp.palette(), qapp.font())
    try:
        theme.apply_theme(qapp)
        janela.resize(1000, 700)
        janela.show()
        qapp.processEvents()

        # Fatia 28: self.grid mora dentro de um container com o breadcrumb
        # em cima, e ESSE container é que fica dentro do QFrame#card.
        grid_card = janela.grid.parentWidget().parentWidget()
        assert grid_card.objectName() == "card"

        img = grid_card.grab().toImage()
        from PySide6.QtGui import QColor

        def px(x, y):
            return QColor(img.pixelColor(x, y)).name().upper()

        # A prova fina de curvatura (comparar quina x meio da aresta) já está
        # em test_theme.py numa sonda isolada, onde a geometria é controlada.
        # Aqui, na janela REAL, o que importa é que a quina do card mostra o
        # fundo — se alguém voltar a arredondar a QListView direto (sem o
        # QFrame#card em volta), o viewport pinta retângulo e isto quebra.
        assert px(1, 1) == theme.BG.upper(), "a quina do card da grade não é curva"
    finally:
        qss, paleta, fonte = antes
        qapp.setStyleSheet(qss)
        qapp.setPalette(paleta)
        qapp.setFont(fonte)


def test_painel_de_detalhes_tem_sinais_de_propriedades(janela):
    assert hasattr(janela.details, "property_value_changed")
    assert hasattr(janela.details, "manage_properties_requested")
    assert hasattr(janela, "_on_property_value_changed")
    assert hasattr(janela, "_manage_properties")


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


def test_smart_collection_nenhuma_aplicada_reseta_filtros(janela):
    """Relatado pelo Rafael: voltar pro '(nenhuma aplicada)' deixava os
    filtros da Smart Collection anterior parados em vez de mostrar tudo."""
    janela.type_filter.set_selected(["texture"])
    janela._apply_filters()
    janela._on_save_smart_collection("Só texturas")  # já deixa o painel na raiz
    assert janela.model.rowCount() == 1

    salva = janela.smart_collections.item(1)
    janela.smart_collections.setCurrentItem(salva)  # sai da raiz de propósito
    assert janela.type_filter.selected() == ["texture"]

    raiz = janela.smart_collections.item(0)
    assert raiz.text() == "(nenhuma aplicada)"
    janela.smart_collections.setCurrentItem(raiz)  # volta pra raiz — dispara o reset

    assert janela.type_filter.selected() == []
    assert janela.model.rowCount() == 2  # volta a mostrar tudo


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
    assert janela.duplicates_action.isEnabled()


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


def test_batch_rename_selected_existe(janela):
    assert hasattr(janela, "_batch_rename_selected")
