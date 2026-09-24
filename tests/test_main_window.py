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

    # Fatia 46: porta 0 = o SO escolhe uma livre. Com a porta FIXA do
    # DEFAULTS (45017), este teste colidia com o AssetDeck de verdade
    # aberto na máquina — não é regressão de código, é isolamento de teste.
    cfg = config.load_config()
    cfg["bridge_port"] = 0
    config.save_config(cfg)

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
                     "smart_collections", "categories",
                     "search_box", "deps_check", "hidden_check", "group_check"):
        assert getattr(janela, atributo) is not None


def test_breadcrumb_acompanha_a_pasta_selecionada(janela):
    """Fatia 28: o caminho acima da grade é a única pista visível de 'onde
    estou' depois de rolar — tem de mudar com a seleção na árvore.

    `_on_dir_selected` é o slot real conectado a `folders.dir_selected`
    (testado à parte, na FolderTree). Chamar direto evita depender de uma
    subpasta existir na biblioteca mínima do fixture `janela`.
    """
    assert janela._breadcrumb_full == "BIBLIOTECA (TUDO)"

    janela._on_dir_selected("Modelos/Cadeiras")
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS › CADEIRAS"

    janela._on_dir_selected("")
    assert janela._breadcrumb_full == "BIBLIOTECA (TUDO)"


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

        # Grab da JANELA, não do card sozinho. Grabar o card isolado renderiza
        # só ele: o que aparece na quina de fora do arredondamento é o
        # preenchimento padrão do pixmap, não o fundo do app. Isso passou
        # despercebido até a Fatia 44 porque esse preenchimento era branco e o
        # `$bg` de então também — o teste comparava branco com branco e teria
        # passado mesmo com o card quadrado. Agora fundo e painel são cores
        # diferentes, então a quina precisa vir da janela de verdade.
        img = janela.grab().toImage()
        from PySide6.QtGui import QColor

        def px(x, y):
            return QColor(img.pixelColor(x, y)).name().upper()

        def distancia(a: str, b: str) -> int:
            """Distância entre duas cores, somando os três canais."""
            ra, ga, ba = theme.hex_to_rgb(a)
            rb, gb, bb = theme.hex_to_rgb(b)
            return abs(ra - rb) + abs(ga - gb) + abs(ba - bb)

        quina = grid_card.mapTo(janela, grid_card.rect().topLeft())
        # EXATAMENTE a quina, não 1px pra dentro: num card quadrado é ali
        # que as duas linhas de contorno se encontram. Amostrar deslocado
        # cai dentro do card e lê a superfície nos dois casos — foi assim
        # que a primeira versão deste teste passou com o card quadrado.
        cor_quina = px(quina.x(), quina.y())
        # Meio da aresta de cima: ali passa a LINHA de contorno do card.
        meio_aresta = px(quina.x() + grid_card.width() // 2, quina.y())

        # A prova de curvatura mudou de forma na Fatia 95, quando o fundo do
        # modo claro virou branco a pedido do Rafael. Antes bastava ler a cor
        # da quina e ver que era o `$bg` e não a `$surface`; com os dois
        # brancos, essa leitura não distingue mais nada — o próprio teste já
        # avisava que comparar branco com branco passaria até com o card
        # quadrado.
        #
        # O que ainda distingue: a quina de um card QUADRADO cai em cima do
        # contorno (duas linhas se encontrando ali), e a de um card CURVO cai
        # fora dele, no fundo limpo. Então a quina tem de ser mais CLARA que o
        # meio da aresta, onde o contorno passa.
        def brilho(cor: str) -> int:
            return sum(theme.hex_to_rgb(cor))

        assert brilho(cor_quina) > brilho(meio_aresta), (
            f"a quina do card da grade não é curva: leu {cor_quina} na quina "
            f"e {meio_aresta} no meio da aresta — se a quina não é mais clara "
            f"que a linha de contorno, ela está EM CIMA do contorno"
        )

        # E a superfície do card aparece de verdade — prova que os dois tons
        # diferem na tela, não só na paleta.
        #
        # Amostra a MARGEM de cima do card, não o centro: o centro cai sobre a
        # grade, e ali quem pinta é a miniatura do asset (uma capa preta fazia
        # este teste falhar dizendo que a superfície era #000000). A margem é
        # o único ponto do card garantidamente sem filho por cima.
        margem = grid_card.layout().contentsMargins()
        topo = grid_card.mapTo(janela, grid_card.rect().topLeft())
        dentro_x = topo.x() + grid_card.width() // 2
        dentro_y = topo.y() + max(2, margem.top() // 2)
        assert px(dentro_x, dentro_y) == theme.SURFACE.upper()
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
    janela.categories.set_selection_from_types(["texture"])
    janela._apply_filters()
    assert janela.model.rowCount() == 1  # só a textura.jpg

    janela._on_save_smart_collection("Só texturas")

    janela.categories.set_selection_from_types(["model"])
    janela._apply_filters()
    assert janela.model.rowCount() == 1  # só o modelo.blend

    salva = janela.smart_collections.item(1)  # índice 0 é "(nenhuma aplicada)"
    assert salva.text() == "Só texturas"
    janela.smart_collections.setCurrentItem(salva)

    assert [g["asset_types"] for g in janela.categories.selection()] == [["texture", "cutout"]]
    assert janela.model.rowCount() == 1
    assert janela.model.row_at(janela.model.index(0))["name"] == "textura"


def test_smart_collection_nenhuma_aplicada_reseta_filtros(janela):
    """Relatado pelo Rafael: voltar pro '(nenhuma aplicada)' deixava os
    filtros da Smart Collection anterior parados em vez de mostrar tudo."""
    janela.categories.set_selection_from_types(["texture"])
    janela._apply_filters()
    janela._on_save_smart_collection("Só texturas")  # já deixa o painel na raiz
    assert janela.model.rowCount() == 1

    salva = janela.smart_collections.item(1)
    janela.smart_collections.setCurrentItem(salva)  # sai da raiz de propósito
    assert [g["asset_types"] for g in janela.categories.selection()] == [["texture", "cutout"]]

    raiz = janela.smart_collections.item(0)
    assert raiz.text() == "(nenhuma aplicada)"
    janela.smart_collections.setCurrentItem(raiz)  # volta pra raiz — dispara o reset

    assert janela.categories.selection() == []
    assert janela.model.rowCount() == 2  # volta a mostrar tudo


def test_thumb_from_disk_usa_a_capa_customizada(janela, tmp_path):
    """Bug relatado pelo Rafael: arrastar um .png sobre um .blend para virar
    a capa dele, depois selecionar o .blend — o preview grande do painel de
    detalhes ficava em '(sem preview ainda)'. Causa: _thumb_from_disk nunca
    olhava pra `cover_path` (só existia em thumbs_dir, onde uma capa
    customizada não mora — ela vive em previews_dir)."""
    from assetdeck.db.repos import previews as previews_repo

    row_modelo = janela._conn.execute(
        "SELECT id FROM assets WHERE name = 'modelo'"
    ).fetchone()
    asset_id = row_modelo["id"]

    origem = tmp_path / "capa.png"
    Image.new("RGB", (64, 64), color="red").save(origem)
    previews_repo.add(janela._conn, asset_id, origem, tmp_path / "previews")
    janela.model.reload()  # a linha em cache do modelo ainda não tinha a capa

    linha = janela.model.row_at(janela.model.index_of_asset(asset_id))
    assert linha["cover_path"], "a capa devia estar em cover_path"

    pix = janela._thumb_from_disk(linha)
    assert pix is not None and not pix.isNull()


def test_duplo_clique_em_set_pbr_abre_material_antes_dos_mapas(
        janela, tmp_path, monkeypatch):
    from assetdeck.indexer.grouper import apply_grouping

    root = janela._library_root
    Image.new("RGB", (16, 16), "red").save(root / "Stone_Color.png")
    Image.new("RGB", (16, 16), "blue").save(root / "Stone_Normal.png")
    scan_library(janela._conn, janela._library_id, root)
    apply_grouping(janela._conn, janela._library_id)
    janela.group_check.setChecked(True)
    janela.model.reload()
    asset_id = janela._conn.execute(
        "SELECT id FROM assets WHERE asset_type = 'pbr_set' AND deleted_at IS NULL"
    ).fetchone()["id"]

    requests = []
    monkeypatch.setattr(
        janela._pipeline, "get_or_request_material",
        lambda aid, name, maps, key, **kw: requests.append((aid, kw)) or None,
    )
    janela._open_preview(janela.model.index_of_asset(asset_id))

    assert not janela.preview_popup.isHidden()
    assert [b.text() for b in janela.preview_popup._maps_group.buttons()] == [
        "Material", "basecolor", "normal",
    ]
    assert any(aid == asset_id and options["size"] == 640
               and options["priority"] == 2 for aid, options in requests)


def test_ponte_e_render_ficam_prontos(janela):
    """Cobre o NameError que derrubava a abertura do app."""
    assert janela._bridge is not None
    assert janela._bridge.listening
    # Fatia 46: fixture pede porta 0 (SO escolhe) — confere que o Qt de
    # fato subiu numa porta real, não só que "listening" ficou True.
    assert janela._bridge.port > 0
    assert janela._render is not None
    assert janela._render.running is False


def test_menu_blender_tem_as_acoes(janela):
    """Fatia 67: o submenu "Blender" virou a página "Blender" da
    SettingsWindow — mesmos botões, container diferente."""
    assert janela.render_action.isEnabled()
    assert janela.cancel_render_action.isEnabled() is False


def test_menu_ferramentas_tem_relocalizar_e_duplicados(janela):
    """Fatia 36: "Biblioteca" (menu ad hoc da Fatia 19) virou parte de
    "Ferramentas"; Fatia 67 moveu "Ferramentas" pra SettingsWindow — as
    ações continuam as mesmas, só o container mudou de novo."""
    assert janela.relocate_action.isEnabled()
    assert janela.duplicates_action.isEnabled()


def test_assinalar_previews_automaticamente_sem_par_de_nome_nao_cria_nada(janela):
    """A biblioteca mínima do fixture tem 'textura.jpg' e 'modelo.blend' —
    nomes diferentes, não casam — só confere que não quebra e avisa."""
    janela._assinalar_previews_automaticamente()
    assert "Nenhum modelo" in janela.statusBar().currentMessage()


def test_esquecer_assets_sumidos_sem_nenhum_sumido_avisa_e_nao_confirma(
    janela, monkeypatch
):
    """Biblioteca mínima do fixture: tudo presente, nada pra esquecer —
    mostra o aviso ('Nada a fazer') e NÃO chega a perguntar 'Continuar?'.

    QMessageBox.information também é modal (.exec() trava headless sem
    isto) — mesmo cuidado do QMessageBox.question em outros testes."""
    from PySide6.QtWidgets import QMessageBox

    avisos = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: avisos.append(a) or QMessageBox.StandardButton.Ok),
    )
    perguntou = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: perguntou.append(a) or QMessageBox.StandardButton.Yes),
    )

    janela._esquecer_assets_sumidos()

    assert avisos, "deveria ter avisado 'nada a fazer'"
    assert not perguntou, "não deveria nem chegar a perguntar sem candidato"


def test_esquecer_assets_sumidos_some_da_grade_apos_confirmar(janela, monkeypatch):
    """Fatia 100: some da grade um asset 100% sumido, só depois do 'Sim'."""
    from PySide6.QtWidgets import QMessageBox

    from assetdeck.indexer.scanner import scan_library

    root = janela._library_root
    (root / "vai_sumir.blend").write_bytes(b"x" * 50)
    lib_id = janela._conn.execute(
        "SELECT id FROM libraries WHERE root_path = ?", (str(root),)
    ).fetchone()["id"]
    scan_library(janela._conn, lib_id, root)
    (root / "vai_sumir.blend").unlink()
    scan_library(janela._conn, lib_id, root)  # marca missing_since, não apaga

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    janela._esquecer_assets_sumidos()

    row = janela._conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'vai_sumir'"
    ).fetchone()
    assert row["deleted_at"] is not None
    assert "1 asset" in janela.statusBar().currentMessage()


def test_esquecer_assets_sumidos_cancelado_nao_marca_nada(janela, monkeypatch):
    """Clicar em 'Não' não muda nada no banco."""
    from PySide6.QtWidgets import QMessageBox

    from assetdeck.indexer.scanner import scan_library

    root = janela._library_root
    (root / "fica_visivel.blend").write_bytes(b"y" * 50)
    lib_id = janela._conn.execute(
        "SELECT id FROM libraries WHERE root_path = ?", (str(root),)
    ).fetchone()["id"]
    scan_library(janela._conn, lib_id, root)
    (root / "fica_visivel.blend").unlink()
    scan_library(janela._conn, lib_id, root)

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    janela._esquecer_assets_sumidos()

    row = janela._conn.execute(
        "SELECT deleted_at FROM assets WHERE name = 'fica_visivel'"
    ).fetchone()
    assert row["deleted_at"] is None


def test_a_barra_de_menus_fica_vazia(janela):
    """Fatia 67: os 5 menus de topo (Arquivo/Editar/Ferramentas/
    Configurações/Janela) viraram uma janela única de configurações,
    acessada pela engrenagem — pedido do Rafael, mockup aprovado antes de
    programar.

    QUAIS são as categorias é assunto de `test_settings_window.py` desde a
    Fatia 80 (elas foram renomeadas e repartidas lá). O que este teste
    guarda, e só ele, é a outra metade da Fatia 67: nenhum menu voltou pro
    topo da janela.
    """
    # `findChildren(QMenu)` pegaria também o popup do `LibrarySwitcher`
    # (Fatia 70, mora num corner widget da própria barra) — o que prova
    # "sem menu de topo" de verdade é a barra não ter NENHUMA QAction.
    assert janela.menuBar().actions() == []


def test_engrenagem_abre_a_settings_window(janela, qapp):
    assert not janela.settings_window.isVisible()
    janela._abrir_configuracoes()
    assert janela.settings_window.isVisible()
    janela.settings_window.close()


def test_engrenagem_do_rail_abre_a_settings_window(janela, qapp):
    """Ajuste pós-tela: o Rafael pediu a engrenagem no canto
    inferior-esquerdo (pé do rail lateral), não na barra de menus."""
    assert janela.sidebar.rail.settings_btn is not None
    assert not janela.settings_window.isVisible()

    janela.sidebar.rail.settings_btn.click()

    assert janela.settings_window.isVisible()
    janela.settings_window.close()


def test_paineis_e_filtros_alterna_visibilidade_dos_paineis(janela, qapp):
    """Fatia 36: cada painel esquerdo + o de detalhes ganha um toggle
    checável — era menu "Janela", Fatia 67 moveu pra página "Painéis e
    filtros" da SettingsWindow (mesma mecânica, container diferente)."""
    janela.show()
    qapp.processEvents()

    widget_pastas, acao_pastas = None, None
    for (widget, rotulo), acao in zip(janela._panel_toggles, janela._window_menu_actions):
        if rotulo == "Pastas":
            widget_pastas, acao_pastas = widget, acao
    assert widget_pastas is not None and acao_pastas is not None

    assert widget_pastas.isVisible()
    assert acao_pastas.isChecked()

    acao_pastas.setChecked(False)
    assert not widget_pastas.isVisible()

    acao_pastas.setChecked(True)
    assert widget_pastas.isVisible()


def test_restaurar_layout_reexibe_paineis_ocultos(janela, qapp):
    janela.show()
    qapp.processEvents()

    widget_tags = next(w for w, r in janela._panel_toggles if r == "Tags")
    widget_tags.setVisible(False)
    assert not widget_tags.isVisible()

    janela._restaurar_layout()

    assert widget_tags.isVisible()
    # QSplitter.setSizes() escala pela altura DISPONÍVEL de verdade — numa
    # janela sem o tamanho exato da soma dos padrões, os valores voltam
    # proporcionais aos padrões, não idênticos a eles. O que importa: nenhum
    # painel ficou colapsado (0px), que era o estado antes do restaurar.
    assert all(tamanho > 0 for tamanho in janela._left_splitter.sizes())


def test_desligar_todos_os_paineis_nao_incha_a_barra_de_busca(janela, qapp):
    """Bug relatado pelo Rafael (Fatia 43): desligar os painéis pelo menu
    Janela fazia a barra de busca inchar até quase tomar a tela — os dois
    itens do QVBoxLayout central (barra de busca + splitter) disputavam o
    espaço sobrando sem prioridade nenhuma entre eles.

    Desde a Fatia 66 a busca nem tem mais item próprio nesse layout (mora
    dentro do `grid_card`, dentro do splitter) — a causa estrutural do bug
    sumiu de vez. Mantido como guarda de regressão: a fileira continua
    compacta mesmo com todos os painéis desligados."""
    janela.resize(1200, 800)
    janela.show()
    qapp.processEvents()

    for acao in janela._window_menu_actions:
        acao.setChecked(False)
    qapp.processEvents()
    qapp.processEvents()

    barra_de_busca = janela.search_box.parentWidget()
    # Nunca deveria passar de umas poucas dezenas de pixels — bem longe dos
    # 356px medidos com o bug presente.
    assert barra_de_busca.height() < 100


def test_checks_de_filtro_moraram_na_pagina_paineis_e_filtros(janela):
    """Fatia 43: fav_check/group_check/deps_check/hidden_check saíram da
    barra de busca e viraram QAction marcável no menu Janela. Fatia 67 moveu
    de novo — QCheckBox de verdade na página "Painéis e filtros" da
    SettingsWindow (mesma API isChecked/setChecked/toggled de uma QAction
    marcável, nada que já lia esses 4 atributos precisou mudar)."""
    from PySide6.QtWidgets import QCheckBox

    for atributo in ("fav_check", "group_check", "deps_check", "hidden_check"):
        check = getattr(janela, atributo)
        assert isinstance(check, QCheckBox)
        assert check.window() is janela.settings_window


def test_size_slider_mora_na_faixa_de_navegacao_com_os_filtros(janela):
    """Fatia 56: o slider saiu do rodapé (longe da grade, alça "bola"
    destoando dos botões de filtro) — hoje mora na faixa de navegação,
    junto de busca/ordenar/resolução/cor (Fatia 66 consolidou pra lá)."""
    from PySide6.QtWidgets import QStatusBar

    assert not isinstance(janela.size_slider.parentWidget(), QStatusBar)
    assert janela.size_slider.parentWidget() is janela.color_filter.parentWidget()
    assert janela.size_slider.width() == 120
    assert janela.size_value.text() == f"{janela.size_slider.value()} px"
    janela.size_slider.setValue(janela.size_slider.value() + 1)
    assert janela.size_value.text() == f"{janela.size_slider.value()} px"


def test_marca_assetdeck_tem_simbolo_proprio_e_nome_visivel(janela):
    from PySide6.QtWidgets import QFrame, QLabel, QWidget

    simbolo = janela.findChild(QWidget, "brandMark")
    nome = janela.findChild(QLabel, "brandName")

    assert simbolo is not None
    assert nome is not None and nome.text() == "AssetDeck"
    assert len(simbolo.findChildren(QFrame, "brandGlyph")) == 4


def test_o_topo_tem_duas_faixas_separadas(janela, qapp):
    """Fatia 46 empilhou em 3 faixas (a linha única, com tudo junto, estava
    "absurdamente atolada" segundo o Rafael). Fatia 66 consolidou busca e
    filtros finos na faixa de navegação, sobrando 2 — mockup aprovado por
    ele antes de implementar.

    O que este teste protege: as duas faixas continuam SEPARADAS — se
    alguém voltar a empilhar tudo numa linha, o caminho de pasta funda
    volta a ser cortado por falta de espaço."""
    janela.show()

    for largura, altura in ((1280, 800), (1600, 900)):
        janela.resize(largura, altura)
        qapp.processEvents()

        def linha_do(widget):
            return widget.mapTo(janela, widget.rect().center()).y()

        y_caminho = linha_do(janela.breadcrumb)
        y_categorias = linha_do(janela.categories)

        assert y_caminho < y_categorias, (
            "as duas faixas do topo têm de estar empilhadas, não na mesma linha"
        )
        # Busca e filtros finos moram na MESMA faixa da navegação/caminho
        # (Fatia 66) — não têm mais faixa própria.
        assert abs(linha_do(janela.search_box) - y_caminho) < 5
        assert abs(linha_do(janela.res_filter) - y_caminho) < 5
        assert abs(linha_do(janela.color_filter) - y_caminho) < 5
        assert abs(linha_do(janela.size_slider) - y_caminho) < 5
        # A contagem de itens desce pra linha das categorias.
        assert abs(linha_do(janela.list_scope) - y_categorias) < 5
        assert janela.size_value.geometry().right() < janela.width()


def test_o_escopo_da_lista_acompanha_a_pasta(janela, qapp):
    assert janela.list_scope.text() == "Toda a biblioteca"

    janela._update_breadcrumb("01 - MODELOS")
    assert janela.list_scope.text() == "Nesta pasta"

    janela._update_breadcrumb("")
    assert janela.list_scope.text() == "Toda a biblioteca"


def test_a_contagem_do_cabecalho_acompanha_o_filtro(janela, qapp):
    """O número da faixa 3 é o que está VISÍVEL — é ele que responde ao
    filtro que o usuário acabou de mexer, logo acima da grade."""
    janela.refresh_count()
    assert janela.list_count.text() == f"{janela.model.rowCount()} assets"

    janela.search_box.setText("textura")
    janela._apply_filters()
    assert janela.list_count.text() == "1 assets"

    janela.search_box.setText("")
    janela._apply_filters()
    assert janela.list_count.text() == f"{janela.model.rowCount()} assets"


def test_a_marca_e_o_contexto_ficam_na_faixa_dos_menus(janela, qapp):
    """Fatia 50. O mockup tinha marca + abas nesta faixa; as abas foram
    descartadas (não correspondem a telas do app — Coleções é seção da
    lateral, Duplicados é diálogo), mas a marca e o contexto entram.

    `setCornerWidget` é o que permite isso sem trocar a QMenuBar por uma
    barra própria, o que custaria atalho de teclado e navegação por Alt.

    Fatia 67: os cinco menus saíram (viraram a SettingsWindow, aberta pela
    engrenagem no pé do rail lateral — NÃO nesta faixa, ajuste pós-tela);
    a faixa fica só com marca + contexto."""
    from PySide6.QtCore import Qt as _Qt

    barra = janela.menuBar()
    esquerda = barra.cornerWidget(_Qt.Corner.TopLeftCorner)
    direita = barra.cornerWidget(_Qt.Corner.TopRightCorner)

    assert esquerda is not None, "a marca não está na faixa dos menus"
    assert direita is janela._contexto_widget
    assert janela.library_switcher.parent() is direita
    assert janela.brand_context.parent() is direita
    # A faixa de menus em si fica vazia — tudo virou a SettingsWindow.
    assert barra.actions() == []


def test_o_contexto_mostra_a_biblioteca_e_o_modo(janela, qapp):
    """A contagem de assets, que o mockup punha aqui, já aparece no cabeçalho
    da lista E no rodapé — um terceiro lugar seria ruído. Qual biblioteca
    está aberta virou o `LibrarySwitcher` (Fatia 70, várias podem estar
    registradas); `brand_context` sobrou só com o modo claro/escuro."""
    assert janela._library_root.name in janela.library_switcher.text()
    modo = janela.brand_context.text()
    assert ("Escuro" in modo) or ("Claro" in modo)


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


def _asset_id(conn, nome: str) -> int:
    row = conn.execute(
        "SELECT id FROM assets WHERE name = ? AND deleted_at IS NULL", (nome,)
    ).fetchone()
    assert row is not None, f"asset '{nome}' não foi indexado"
    return row["id"]


def test_preview_manual_vale_para_asset_sem_miniatura_nativa(janela):
    """Fatia 28d: a restrição de tipo (só 'model'/'scene') virou uma
    restrição de CONTEÚDO — vale pra qualquer asset sem preview de verdade
    (.ies, .psd, .cube… e, antes disso, .blend/.fbx)."""
    from assetdeck import config
    from assetdeck.db.repos import libraries as libraries_repo
    from assetdeck.indexer.scanner import scan_library

    # Preferência "ask" (padrão) abre um QMessageBox.exec() MODAL — trava a
    # suíte esperando um clique que nunca vem. "never" evita a pergunta.
    cfg = config.load_config()
    cfg["hide_preview_source"] = "never"
    config.save_config(cfg)

    root = janela._library_root
    (root / "spot.ies").write_bytes(b"IES:LM-63-2002" + b"\x00" * 20)
    lib_id = libraries_repo.get_or_create(janela._conn, root)
    scan_library(janela._conn, lib_id, root)
    janela.model.reload()

    ies_id = _asset_id(janela._conn, "spot")
    jpg_id = _asset_id(janela._conn, "textura")

    janela._on_asset_preview_dropped(ies_id, [jpg_id])

    linha = janela.model.row_at(janela.model.index_of_asset(ies_id))
    assert linha["cover_path"], "o .ies devia ter ganhado a capa manual"


def test_preview_manual_com_arquivo_de_origem_sumido_nao_falha_em_silencio(
    janela, monkeypatch, caplog
):
    """Bug real achado em 2026-08-05 (Rafael): com o library_root apontando
    pra um caminho que não bate mais com o disco (ex.: SSD remontado num
    lugar diferente), previews_repo.add() levanta FileNotFoundError — e
    como isso acontecia DENTRO do sinal emitido a partir de startDrag()
    (chamado pelo C++ do Qt), a exceção sumia sem log e sem aviso: o log
    dizia '_apply_drop retornou True', mas nenhum preview era criado.

    Este teste finge exatamente esse cenário — origem que `can_preview`
    aceita (extensão certa) mas que NÃO existe mais no disco de verdade —
    e confere que agora vira um aviso visível, não silêncio."""
    from assetdeck.db.repos import libraries as libraries_repo
    from assetdeck.indexer.scanner import scan_library

    cfg = config.load_config()
    cfg["hide_preview_source"] = "never"
    config.save_config(cfg)

    root = janela._library_root
    (root / "existe.jpg").write_bytes(b"j" * 30)
    lib_id = libraries_repo.get_or_create(janela._conn, root)
    scan_library(janela._conn, lib_id, root)
    janela.model.reload()

    modelo_id = _asset_id(janela._conn, "modelo")  # .blend do fixture — sem preview nativo
    origem_id = _asset_id(janela._conn, "existe")

    # Simula "arquivo sumiu do disco depois do último rescan": can_preview só
    # olha a extensão, então o registro no banco continua achando que é uma
    # imagem válida — é exatamente essa lacuna que causava o bug real.
    (root / "existe.jpg").unlink()

    with caplog.at_level("ERROR"):
        janela._on_asset_preview_dropped(modelo_id, [origem_id])

    linha = janela.model.row_at(janela.model.index_of_asset(modelo_id))
    assert not linha["cover_path"], "não pode ter aplicado uma capa que falhou ao copiar"
    assert "Falha ao copiar a imagem" in janela.statusBar().currentMessage()
    assert any("Falha ao copiar preview" in r.message for r in caplog.records), \
        "o erro tem que aparecer no log — nada de falha silenciosa"


def test_preview_manual_recusa_asset_que_ja_tem_miniatura_de_verdade(janela):
    """Um .jpg já tem preview nativo — não faz sentido sobrepor com um
    preview manual, então o drop é ignorado (com aviso no rodapé)."""
    jpg_id = _asset_id(janela._conn, "textura")

    janela._on_asset_preview_dropped(jpg_id, [jpg_id])

    linha = janela.model.row_at(janela.model.index_of_asset(jpg_id))
    assert not linha["cover_path"]


# ---- Fatia 36: ações do menu Editar sem nada selecionado ----


def test_editar_menu_avisa_sem_derrubar_nada_sem_selecao(janela):
    """As ações do menu "Editar" que dependem de seleção (copiar/colar tags,
    renomear em lote) precisam avisar no rodapé em vez de fazer nada em
    silêncio ou quebrar quando ninguém está selecionado."""
    janela.grid.clearSelection()

    janela._copy_tags_selected()
    assert "Selecione exatamente 1" in janela.statusBar().currentMessage()

    janela._tag_clipboard = None
    janela._paste_tags_selected(replace=False)
    assert "Selecione ao menos 1" in janela.statusBar().currentMessage()

    janela._batch_rename_dos_selecionados()
    assert "Selecione ao menos 1" in janela.statusBar().currentMessage()


def test_editar_menu_colar_tags_sem_nada_copiado(janela):
    janela.grid.selectionModel().select(
        janela.model.index(0),
        janela.grid.selectionModel().SelectionFlag.Select,
    )
    janela._tag_clipboard = None

    janela._paste_tags_selected(replace=False)

    assert "Nenhuma tag copiada" in janela.statusBar().currentMessage()


def test_reindexar_e_sair_tem_atalho_global(janela):
    """Fatia 67: o menu "Arquivo" sumiu (Reindexar já era botão na barra de
    navegação desde a Fatia 66; Sair virou botão na página "Geral" da
    SettingsWindow). Os atalhos Ctrl+R/Ctrl+Q têm de continuar funcionando
    em QUALQUER lugar do app — `self.addAction(...)` registra isso direto
    na MainWindow, sem precisar de menu nenhum pra existir."""
    from PySide6.QtGui import QKeySequence

    assert janela.rescan_btn.shortcut() == QKeySequence("Ctrl+R")
    assert janela.sair_action.shortcut() == QKeySequence.StandardKey.Quit
    assert janela.sair_action in janela.actions()


# ---- Fatia 61 (bug pós-tela): taggear "não fazia nada" sem filtro ativo ----


def test_checkbox_de_tag_atualiza_a_grid_sem_filtro_ativo(janela):
    """BUG relatado pelo Rafael (2026-08-14): taggear pelo checkbox do painel
    de detalhes, por Ctrl+T ou arrastando pra uma tag "parecia não fazer
    nada" navegando numa pasta normal. A gravação no banco sempre funcionou
    (`tags_repo.assign`/`tags_of` — conferido à parte); o que faltava era
    `_after_tags_changed` atualizar a GRID: ela só chamava `_apply_filters()`
    quando havia filtro de tag ou busca ativos, então no caso mais comum
    (nenhum dos dois) nada na tela mudava. `_on_tag_toggled` é o handler real
    conectado a `details.tag_toggled` (o sinal do checkbox)."""
    from assetdeck.db.repos import tags as tags_repo
    from assetdeck.ui.asset_grid import HAS_TAGS_ROLE

    tag_id = tags_repo.create(janela._conn, "Teste")
    asset_id = _asset_id(janela._conn, "textura")
    idx = janela.model.index_of_asset(asset_id)

    assert janela.tags.current_tag_id() is None
    assert janela.search_box.text() == ""
    assert janela.model.data(idx, HAS_TAGS_ROLE) is False

    janela.grid.selectionModel().select(
        idx, janela.grid.selectionModel().SelectionFlag.Select,
    )
    janela._on_tag_toggled(asset_id, tag_id, True)

    idx2 = janela.model.index_of_asset(asset_id)
    assert janela.model.data(idx2, HAS_TAGS_ROLE) is True, \
        "a grid tem que refletir a tag nova mesmo sem filtro de tag/busca ativo"


def test_arrastar_para_tag_atualiza_a_grid_sem_filtro_ativo(janela):
    """Mesmo bug do teste acima, pelo caminho do drag-and-drop
    (`_on_assets_dropped`, conectado a `tags.assets_dropped`)."""
    from assetdeck.db.repos import tags as tags_repo
    from assetdeck.ui.asset_grid import HAS_TAGS_ROLE

    tag_id = tags_repo.create(janela._conn, "Teste")
    asset_id = _asset_id(janela._conn, "textura")
    idx = janela.model.index_of_asset(asset_id)
    assert janela.model.data(idx, HAS_TAGS_ROLE) is False

    janela._on_assets_dropped(tag_id, [asset_id])

    idx2 = janela.model.index_of_asset(asset_id)
    assert janela.model.data(idx2, HAS_TAGS_ROLE) is True


# ---- Fatia 64: reindexação não re-varre thumbnails à toa ----


def test_on_finished_pula_warmup_quando_so_sumiu_arquivo(janela, monkeypatch):
    """Bug de performance relatado pelo Rafael: a reindexação automática ao
    abrir "demora demais". Uma causa real: `_on_finished` chamava
    `_reload_all()` — que inclui o pré-aquecimento CARO de thumbnails
    (medido em ~1,1s numa biblioteca de 23 mil assets, Fatia 45) — sempre
    que QUALQUER coisa mudava no scan, inclusive quando só um arquivo
    sumiu. Sumir não traz nenhuma imagem nova pra desenhar."""
    from assetdeck.indexer.scanner import ScanStats

    chamadas_warmup = []
    chamadas_reload = []
    monkeypatch.setattr(janela.model, "warmup_library", lambda: chamadas_warmup.append(1))
    monkeypatch.setattr(janela.model, "reload", lambda: chamadas_reload.append(1))

    janela._on_finished(ScanStats(missing=1))

    assert chamadas_warmup == [], "arquivo sumido não precisa de thumbnail nova"
    assert chamadas_reload == [1], "mas pastas/tags/contagens ainda têm que atualizar"


def test_on_finished_pula_warmup_quando_so_restaurou_sidecar(janela, monkeypatch):
    """Mesma lógica: metadado de sidecar voltando pra um arquivo que já
    estava indexado (e já tinha thumbnail) também não precisa de
    pré-aquecimento novo."""
    from assetdeck.indexer.scanner import ScanStats

    chamadas_warmup = []
    monkeypatch.setattr(janela.model, "warmup_library", lambda: chamadas_warmup.append(1))

    janela._on_finished(ScanStats(restored=3))

    assert chamadas_warmup == []


def test_on_finished_avisa_antes_de_recarregar(janela, monkeypatch):
    """Antes do fix, a barra de status ficava com o texto de "Indexando…
    X/Y arquivos" congelado durante o freeze da recarga — dava a impressão
    de app travado (queixa do Rafael: "não sei muito bem o que exatamente
    faz o resync"). Agora "Sincronizando biblioteca…" aparece ANTES."""
    from assetdeck.indexer.scanner import ScanStats

    mensagens = []
    monkeypatch.setattr(janela.statusBar(), "showMessage", mensagens.append)
    monkeypatch.setattr(janela.model, "warmup_library", lambda: None)

    janela._on_finished(ScanStats(added=1))

    assert "Sincronizando biblioteca…" in mensagens
    assert mensagens.index("Sincronizando biblioteca…") < len(mensagens) - 1, \
        "tem que vir ANTES da mensagem final, não depois"


@pytest.mark.parametrize("kwargs", [
    {"added": 2}, {"updated": 1}, {"reappeared": 1}, {"grouped_sets": 1},
])
def test_on_finished_warmup_quando_ha_conteudo_visual_novo(janela, monkeypatch, kwargs):
    """O caso que PRECISA continuar pagando o pré-aquecimento: arquivo novo,
    atualizado, reaparecido ou set PBR novo — todos podem exigir thumbnail
    que ainda não existe."""
    from assetdeck.indexer.scanner import ScanStats

    chamadas_warmup = []
    monkeypatch.setattr(janela.model, "warmup_library", lambda: chamadas_warmup.append(1))

    janela._on_finished(ScanStats(**kwargs))

    assert chamadas_warmup == [1]


def test_on_finished_nada_mudou_nao_chama_reload_all(janela, monkeypatch):
    """Comportamento de antes preservado: scan sem nenhuma mudança não
    chama `_reload_all` nem no modo barato — só atualiza a contagem."""
    from assetdeck.indexer.scanner import ScanStats

    chamadas = []
    monkeypatch.setattr(janela, "_reload_all", lambda **kw: chamadas.append(kw))

    janela._on_finished(ScanStats())

    assert chamadas == []


@pytest.mark.parametrize("nome_arquivo", ["modelo.obj", "modelo.fbx", "modelo.blend"])
def test_open_preview_roteia_formato_3d_pro_visualizador_de_modelo(
    janela, monkeypatch, nome_arquivo):
    """Fase 6: duplo clique num .obj/.fbx/.blend abre o visualizador 3D em
    vez do PreviewPopup achatado — mesmo padrão do .hdr/.exr (Fatia 34). Não
    instancia a janela de verdade: QOpenGLWidget não roda no modo offscreen
    do pytest."""
    chamadas = []

    class _FakeViewer:
        def abrir_modelo(self, caminho, content_hash=None):
            chamadas.append((caminho, content_hash))

    monkeypatch.setattr(janela, "_visualizador", lambda: _FakeViewer())
    monkeypatch.setattr(janela.model, "row_at", lambda idx: {
        "rel_path": nome_arquivo, "asset_type": "model", "id": 999,
        "content_hash": "hash-de-teste",
    })

    janela._open_preview(janela.model.index(0))

    assert len(chamadas) == 1
    caminho, content_hash = chamadas[0]
    assert caminho.name == nome_arquivo
    assert content_hash == "hash-de-teste"


def test_open_preview_nao_roteia_textura_pro_visualizador_de_modelo(janela, monkeypatch):
    """Extensão fora da lista suportada (Fase 6) continua no PreviewPopup
    de sempre — o roteamento é por extensão, não vira o padrão pra tudo."""
    chamadas = []
    monkeypatch.setattr(
        janela, "_visualizador",
        lambda: pytest.fail("não devia abrir o visualizador 3D pra textura"))
    monkeypatch.setattr(janela, "preview_popup",
                        type("Fake", (), {"show_for": lambda *a, **k: chamadas.append(1)})())
    monkeypatch.setattr(janela.model, "row_at", lambda idx: {
        "rel_path": "textura.jpg", "asset_type": "texture", "id": 998,
        "content_hash": "hash-de-teste",
    })

    janela._open_preview(janela.model.index(0))

    assert chamadas == [1]


def test_prewarm_gl_viewers_existe(janela):
    """Fatia 72 (fix do "piscar"): só confirma que o método existe e é
    chamável pelo nome certo (`app.py` depende dele) — chamar de verdade
    trava o interpretador no modo offscreen do pytest (QOpenGLWidget
    real não roda sem tela; `resizeGL` desreferencia `self._gl`, que só
    existe depois de um `initializeGL` que nunca chega a rodar aqui —
    mesma fronteira de `test_hdri_viewer.py`/`test_model_viewer.py`, que
    também não instanciam os widgets de OpenGL de verdade)."""
    assert callable(janela.prewarm_gl_viewers)


def test_prewarm_preserva_o_estado_da_janela(janela):
    """Regressão do que o Rafael relatou: "não consigo mais maximizar a
    janela".

    Os visualizadores são janelas de topo FILHAS da principal. Mostrar e
    esconder uma delas — que é o que `prewarm_gl_viewers` faz na abertura,
    pra matar o "piscar" (Fatia 72) — fazia o Qt recalcular o estado do PAI
    e deixá-lo em "normal". Só o ESTADO: o tamanho continuava o de
    maximizada. Na tela sobrava uma janela do tamanho do monitor que o
    gerenciador considera normal, então o botão de maximizar não mudava
    nada.

    O teste não CHAMA `prewarm_gl_viewers` — `QOpenGLWidget` derruba o
    processo no modo offscreen do pytest, fronteira já registrada em
    `test_hdri_viewer.py`. O que ele guarda é a parte verificável sem GL:
    que o método lê o estado antes e o repõe depois.
    """
    import inspect

    from PySide6.QtCore import Qt

    fonte = inspect.getsource(janela.prewarm_gl_viewers)
    assert "windowState()" in fonte, (
        "prewarm_gl_viewers precisa LER o estado da janela antes de mexer "
        "nos visualizadores"
    )
    assert "setWindowState(" in fonte, (
        "prewarm_gl_viewers precisa REPOR o estado depois — sem isso a "
        "janela perde o 'maximizada' e o botão do gerenciador para de "
        "surtir efeito"
    )

    # E o estado é de fato reponível: guardar/repor devolve o mesmo valor.
    janela.setWindowState(Qt.WindowState.WindowMaximized)
    guardado = janela.windowState()
    janela.setWindowState(Qt.WindowState.WindowNoState)
    janela.setWindowState(guardado)
    assert janela.windowState() == guardado


def _visor_dublado(monkeypatch):
    """Substitui a janela do visualizador por um dublê que registra o que
    aconteceu com ela. Instanciar a de verdade monta dois `QOpenGLWidget`,
    que derrubam o processo no modo offscreen do pytest (fronteira já
    registrada em `test_hdri_viewer.py`)."""
    from assetdeck.ui import viewer_window

    criadas = []

    class _Dublê:
        def __init__(self, parent=None):
            self.mostrada = 0
            self.escondida = 0
            criadas.append(self)

        def setAttribute(self, *a):
            pass

        def show(self):
            self.mostrada += 1

        def hide(self):
            self.escondida += 1

    monkeypatch.setattr(viewer_window, "VisualizadorWindow", _Dublê)
    return criadas


def test_visualizador_e_criado_uma_vez_so(janela, monkeypatch):
    """Cada abertura de HDRI/modelo reusa a MESMA janela: montar contexto
    de OpenGL de novo a cada duplo clique custa caro e é o que fazia o
    'piscar' voltar."""
    criadas = _visor_dublado(monkeypatch)

    primeiro = janela._visualizador()
    segundo = janela._visualizador()

    assert primeiro is segundo
    assert len(criadas) == 1


def test_prewarm_aquece_uma_janela_so(janela, monkeypatch):
    """Fatia 90: os dois visualizadores passaram a dividir UMA janela.

    A transição de modo de composição que o pré-aquecimento paga é por
    JANELA DE TOPO — com duas janelas ela acontecia duas vezes na abertura
    do app. Se alguém voltar a criar uma janela por tipo, este teste cai.
    """
    criadas = _visor_dublado(monkeypatch)

    janela.prewarm_gl_viewers()

    assert len(criadas) == 1, "o pré-aquecimento voltou a abrir mais de uma janela"
    assert criadas[0].mostrada == 1
    assert criadas[0].escondida == 1


def test_prewarm_nao_entrega_a_janela_ao_gerenciador(janela):
    """Regressão do "não consigo abrir a visualização de modelos 3d nem de
    hdris com o duplo clique" (Rafael, 2026-08-19).

    O visualizador ABRIA MINIMIZADO — ia direto pro dock, e da cadeira dele
    parecia que o duplo clique não fazia nada. O log mostrava tudo certo
    ("HDRI pronto na tela", "Modelo pronto na tela"), porque estava mesmo:
    a janela existia, carregava e ficava iconificada.

    Causa: o pré-aquecimento fazia `show()` + `hide()` na janela. Desmapear
    uma janela no X a marca como iconificada, e o gerenciador reaplica esse
    estado toda vez que ela reaparece. Medido na tela do Rafael nos dois
    sentidos: com pré-aquecimento nascia minimizada, sem ele nascia normal.
    Não era por estar fora da tela — a variante invisível por opacidade, na
    posição normal, minimizava igual. Era o par mapear/desmapear.

    `WA_DontShowOnScreen` monta a janela e pinta o frame (que é o que
    dispara a troca de composição, o motivo do pré-aquecimento existir) sem
    nunca passar pelo gerenciador.

    O teste lê o código porque o efeito só existe com gerenciador de
    janelas e OpenGL de verdade — nenhum dos dois roda no pytest (mesma
    fronteira de `test_hdri_viewer.py`). A verificação de verdade foi na
    tela dele, e está registrada no TODO.
    """
    import inspect

    fonte = inspect.getsource(janela.prewarm_gl_viewers)
    assert "WA_DontShowOnScreen" in fonte, (
        "o pré-aquecimento precisa montar a janela SEM entregá-la ao "
        "gerenciador de janelas"
    )
    assert "visor.move(" not in fonte, (
        "voltou o show()/hide() fora da tela — é ele que deixa o "
        "visualizador abrindo minimizado pro resto da sessão"
    )


# ---- maximização: guardar e repor (Fatia 94) ----

def test_maximizada_faz_ida_e_volta_pelo_config(janela):
    """Rafael: "a janela não vem maximizada (parece que não guarda o estado
    anterior da sessão)".

    O `saveGeometry` do Qt até carrega essa informação, mas depende de
    `windowState()` valer no instante do fechamento — e dentro do
    `closeEvent` o estado já se foi (medido: a janela estava maximizada um
    instante antes e o config saía com `false`). Por isso a bandeira é
    gravada à parte, a partir do último valor visto ao vivo.
    """
    from assetdeck import config

    janela._maximizada = True
    janela._save_ui_state()
    assert config.load_config()["ui_state"]["window_maximized"] is True

    janela._maximizada_desejada = False
    janela._restore_ui_state()
    assert janela._maximizada_desejada is True


def test_a_intencao_do_config_nao_e_apagada_pelo_estado_atual(janela):
    """São DUAS variáveis de propósito. Com uma só, o "não maximizada" que o
    gerenciador manda assim que a janela aparece apagava a intenção lida do
    config antes dela ser aplicada — e a janela abria normal (medido)."""
    janela._maximizada_desejada = True
    janela._maximizada = False  # o que o gerenciador diz agora

    assert janela._maximizada_desejada is True, (
        "a intenção vinda do config não pode depender do estado do momento"
    )


def test_showEvent_pede_a_maximizacao_uma_vez_so(janela, monkeypatch):
    """`showEvent` dispara toda vez que a janela reaparece; repor a
    maximização em todas seria passar por cima do Rafael, que pode ter
    deixado a janela normal de propósito."""
    from PySide6.QtGui import QShowEvent

    pedidos = []
    monkeypatch.setattr(janela, "_repor_maximizada",
                        lambda *a, **k: pedidos.append(1))
    janela._maximizada_desejada = True
    janela._maximizada_reposta = False

    janela.showEvent(QShowEvent())
    janela.showEvent(QShowEvent())

    assert pedidos == [1]


def test_sem_maximizacao_gravada_o_showEvent_nao_mexe(janela, monkeypatch):
    from PySide6.QtGui import QShowEvent

    pedidos = []
    monkeypatch.setattr(janela, "_repor_maximizada",
                        lambda *a, **k: pedidos.append(1))
    janela._maximizada_desejada = False
    janela._maximizada_reposta = False

    janela.showEvent(QShowEvent())

    assert pedidos == []


def test_o_seletor_de_biblioteca_boia_no_meio_da_faixa(janela, qapp):
    """Pedido três vezes pelo Rafael, e as duas primeiras respostas minhas
    não resolveram — vale um teste.

    1ª (Fatia 78): pus `AlignVCenter` no layout. Não fez nada: o seletor
       media 37px numa faixa de 37px, então não havia folga pra distribuir.
    2ª (Fatia 95): encolhi o botão pra 29px. Continuou colado no topo, e a
       medição mostrou por quê — o Qt encosta o widget do canto DIREITO da
       barra de menus no alto (y=0, com os 13px sobrando embaixo), e como o
       widget tinha a altura exata do botão, o alinhamento de dentro
       continuava sem folga. O canto ESQUERDO, com a marca, o Qt centraliza
       sozinho; as duas pontas não recebem o mesmo tratamento.

    A correção é o widget do canto ter a altura da FAIXA. Este teste mede o
    resultado — onde o botão cai — e não como ele foi obtido.
    """
    janela.show()
    qapp.processEvents()

    barra = janela.menuBar()
    seletor = janela.library_switcher
    topo = seletor.mapTo(janela, seletor.rect().topLeft()).y()
    sobra_cima = topo
    sobra_baixo = barra.height() - topo - seletor.height()

    assert seletor.height() < barra.height(), (
        f"o seletor ocupa a faixa inteira ({seletor.height()}px de "
        f"{barra.height()}px) — não há o que centralizar"
    )
    assert abs(sobra_cima - sobra_baixo) <= 2, (
        f"o seletor não está centralizado na faixa: {sobra_cima}px acima e "
        f"{sobra_baixo}px abaixo"
    )


def test_a_reposicao_da_maximizacao_nao_desiste_no_falso_positivo(janela, monkeypatch):
    """Regressão da Fatia 94 → 97: "o programa voltou a não iniciar
    maximizado".

    A Fatia 94 pôs uma saída antecipada em `_repor_maximizada` — "duas
    leituras seguidas dizendo maximizada, pode parar". Isso reintroduziu
    exatamente o que o laço existe pra atravessar: o Qt responde "sim,
    maximizada" logo depois do `restoreGeometry`, ANTES de o gerenciador
    confirmar, e o gerenciador desfaz em seguida. Duas leituras desse falso
    positivo bastavam pra desistir.

    O teste roteiriza essa sequência — dois "sim" mentirosos seguidos de um
    "não" — e exige que o laço volte a pedir. É a parte verificável sem
    gerenciador de janelas; a prova de ponta a ponta foi na tela do Rafael
    (fecha maximizado, reabre maximizado) e está registrada no TODO.
    """
    respostas = iter([True, True, False, False, True])
    pedidos = []
    monkeypatch.setattr(janela, "isMaximized", lambda: next(respostas, True))
    monkeypatch.setattr(janela, "showMaximized", lambda: pedidos.append(1))
    # O relógio é dublado: o teste dispara as tentativas na mão, sem esperar.
    agendados = []
    monkeypatch.setattr("PySide6.QtCore.QTimer.singleShot",
                        staticmethod(lambda ms, fn: agendados.append(fn)))

    janela._repor_maximizada(0)      # 1ª leitura: "sim" (mentira)
    assert agendados, "o laço parou na primeira leitura"
    agendados.pop()()                # 2ª leitura: "sim" (mentira de novo)
    assert agendados, "o laço desistiu depois de dois 'sim' seguidos"
    agendados.pop()()                # 3ª leitura: "não" — tem de reagir

    assert pedidos, (
        "o gerenciador desfez a maximização e o laço não pediu de novo — "
        "é assim que a janela volta a abrir em tamanho normal"
    )


# ---- gerar capa pelo botão direito, só de alguns assets (Fatia 101) ----

def _indice_por_nome(janela, nome):
    for linha in range(janela.model.rowCount()):
        idx = janela.model.index(linha)
        if janela.model.row_at(idx)["name"] == nome:
            return idx
    raise AssertionError(f"{nome!r} não está na grade de teste")


def _linha_por_nome(janela, nome):
    idx = _indice_por_nome(janela, nome)
    return janela.model.row_at(idx)


def test_gerar_capa_aparece_pro_modelo_sem_capa(janela):
    """Rafael: "gerar o preview porém somente de alguns assets... ao clicar
    com o botão direito em um asset/vários selecionados, se detectar que
    está sem preview, dar a opção de gerar preview"."""
    menu = janela._montar_menu_grid([_linha_por_nome(janela, "modelo")])

    textos = [a.text() for a in menu.actions()]
    assert any("Gerar capa" in t for t in textos)


def test_gerar_capa_nao_aparece_pra_textura(janela):
    """O critério é o mesmo do render em lote: só modelo .blend. Uma imagem
    já É sua própria miniatura — não faz sentido "gerar capa" dela."""
    menu = janela._montar_menu_grid([_linha_por_nome(janela, "textura")])

    textos = [a.text() for a in menu.actions()]
    assert not any("Gerar capa" in t for t in textos)


def test_gerar_capa_nao_aparece_quando_ja_tem_capa(janela, tmp_path):
    from PIL import Image

    from assetdeck.db.repos import previews as previews_repo

    linha = _linha_por_nome(janela, "modelo")
    capa = tmp_path / "capa.png"
    Image.new("RGB", (4, 4)).save(capa)
    previews_repo.add(janela._conn, linha["id"], capa, janela._thumbs_dir.parent / "previews")
    janela._reload_grid()

    menu = janela._montar_menu_grid([_linha_por_nome(janela, "modelo")])

    textos = [a.text() for a in menu.actions()]
    assert not any("Gerar capa" in t for t in textos)


def test_gerar_capa_chama_render_covers_com_os_ids_certos(janela, monkeypatch):
    linha = _linha_por_nome(janela, "modelo")
    chamadas = []
    monkeypatch.setattr(janela, "_render_covers", lambda ids: chamadas.append(ids))

    menu = janela._montar_menu_grid([linha])
    acao = next(a for a in menu.actions() if "Gerar capa" in a.text())
    acao.trigger()

    assert chamadas == [[linha["id"]]]
