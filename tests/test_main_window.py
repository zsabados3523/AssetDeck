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
        cor_quina = px(quina.x() + 1, quina.y() + 1)

        # A prova fina de curvatura (comparar quina x meio da aresta) já está
        # em test_theme.py numa sonda isolada, onde a geometria é controlada.
        # Aqui, na janela REAL, o que importa é que a quina do card mostra o
        # FUNDO e não o painel — se alguém voltar a arredondar a QListView
        # direto (sem o QFrame#card em volta), o viewport pinta retângulo, a
        # quina passa a ser a superfície, e isto quebra.
        #
        # Não dá pra exigir igualdade exata com `$bg`: a sombra do card
        # escurece alguns pontos ao redor da quina (~2 níveis por canal). Ela
        # só passou a aparecer na Fatia 44, quando o fundo deixou de ser
        # branco puro — antes a sombra caía sobre branco e sumia.
        assert distancia(cor_quina, theme.BG) < distancia(cor_quina, theme.SURFACE), \
            f"a quina do card da grade não é curva (leu {cor_quina})"

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


def test_ponte_e_render_ficam_prontos(janela):
    """Cobre o NameError que derrubava a abertura do app."""
    assert janela._bridge is not None
    assert janela._bridge.listening
    # Fatia 46: fixture pede porta 0 (SO escolhe) — confere que o Qt de
    # fato subiu numa porta real, não só que "listening" ficou True.
    assert janela._bridge.port > 0
    assert janela._render is not None
    assert janela._render.running is False


def _titulos_dos_menus(janela):
    """Todos os QMenu da barra, recursivo (pega submenu tipo "Blender"
    dentro de "Ferramentas") — findChildren atravessa a árvore de objetos
    Qt inteira, não só o primeiro nível."""
    from PySide6.QtWidgets import QMenu

    return [m.title() for m in janela.menuBar().findChildren(QMenu)]


def test_menu_blender_tem_as_acoes(janela):
    assert any("Blender" in t for t in _titulos_dos_menus(janela))
    assert janela.render_action.isEnabled()
    assert janela.cancel_render_action.isEnabled() is False


def test_menu_ferramentas_tem_relocalizar_e_duplicados(janela):
    """Fatia 36: "Biblioteca" (menu ad hoc da Fatia 19) virou parte de
    "Ferramentas" — as ações continuam as mesmas, só o container mudou."""
    assert any("Ferramentas" in t for t in _titulos_dos_menus(janela))
    assert janela.relocate_action.isEnabled()
    assert janela.duplicates_action.isEnabled()


def test_menu_ferramentas_tem_assinalar_previews_automaticamente(janela):
    """Fatia 57: rodar o casamento por nome igual sob demanda, sem esperar
    a próxima varredura."""
    textos = [a.text() for a in janela._menu_ferramentas.actions()]
    assert any("previews automaticamente" in t for t in textos)


def test_assinalar_previews_automaticamente_sem_par_de_nome_nao_cria_nada(janela):
    """A biblioteca mínima do fixture tem 'textura.jpg' e 'modelo.blend' —
    nomes diferentes, não casam — só confere que não quebra e avisa."""
    janela._assinalar_previews_automaticamente()
    assert "Nenhum modelo" in janela.statusBar().currentMessage()


def test_barra_de_menus_tem_os_cinco_menus(janela):
    """Fatia 36: Arquivo, Editar, Ferramentas, Configurações, Janela —
    antes só existiam "Biblioteca" e "Blender" soltos.

    Usa `janela._top_menus` (referência guardada na própria MainWindow), não
    `menuBar().actions()[i].menu()` — reconstruir o QMenu a partir da QAction
    se mostrou frágil nesta versão do PySide6/shiboken (achado escrevendo
    este teste: o wrapper Python intermediário podia derrubar o QMenu de
    verdade). Ver `_setup_menu_bar`."""
    topo = [m.title() for m in janela._top_menus]
    for esperado in ("Arquivo", "Editar", "Ferramentas", "Configurações", "Janela"):
        assert any(esperado in t for t in topo), f"menu {esperado!r} não encontrado em {topo}"


def test_menu_janela_alterna_visibilidade_dos_paineis(janela, qapp):
    """Fatia 36: cada painel esquerdo + o de detalhes ganha um toggle
    checável no menu "Janela"."""
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
    itens do QVBoxLayout central disputavam o espaço sobrando sem
    prioridade nenhuma entre eles. `setStretchFactor` garante que o
    splitter (painéis + grade) sempre fica com o espaço extra."""
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


def test_checks_de_filtro_moraram_no_menu_janela(janela):
    """Fatia 43: fav_check/group_check/deps_check/hidden_check saíram da
    barra de busca e viram QAction marcável no menu Janela."""
    from PySide6.QtGui import QAction

    for atributo in ("fav_check", "group_check", "deps_check", "hidden_check"):
        acao = getattr(janela, atributo)
        assert isinstance(acao, QAction)
        assert acao.isCheckable()
        assert acao in janela._menu_janela.actions()


def test_size_slider_mora_na_faixa_de_nota_resolucao_e_cor(janela):
    """Fatia 56: o slider saiu do rodapé (longe da grade, alça "bola"
    destoando dos botões de filtro) e foi pra faixa 3, ao lado de
    nota/resolução/cor — mesma linha que já refina o que está na tela."""
    from PySide6.QtWidgets import QStatusBar

    assert not isinstance(janela.size_slider.parentWidget(), QStatusBar)
    assert janela.size_slider.parentWidget() is janela.color_filter.parentWidget()


def test_o_topo_tem_tres_faixas_separadas(janela, qapp):
    """Fatia 46. O Rafael olhou a linha única (navegação + caminho + 6
    categorias + 3 filtros) e disse que estava "absurdamente atolado".

    Cada faixa responde uma pergunta diferente, e o que este teste protege é
    que elas continuem SEPARADAS — se alguém voltar a empilhar tudo numa
    linha, o caminho de pasta funda volta a ser cortado por falta de espaço.
    """
    janela.resize(1200, 800)
    janela.show()
    qapp.processEvents()

    def linha_do(widget):
        return widget.mapTo(janela, widget.rect().center()).y()

    y_caminho = linha_do(janela.breadcrumb)
    y_categorias = linha_do(janela.categories)
    y_escopo = linha_do(janela.list_scope)

    assert y_caminho < y_categorias < y_escopo, (
        "as três faixas do topo têm de estar empilhadas, não na mesma linha"
    )
    # Os filtros finos moram na MESMA faixa do escopo da lista (agem sobre a
    # lista que já está na tela), não junto das categorias.
    assert abs(linha_do(janela.res_filter) - y_escopo) < 5
    assert abs(linha_do(janela.color_filter) - y_escopo) < 5


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
    """
    from PySide6.QtCore import Qt as _Qt

    barra = janela.menuBar()
    esquerda = barra.cornerWidget(_Qt.Corner.TopLeftCorner)
    direita = barra.cornerWidget(_Qt.Corner.TopRightCorner)

    assert esquerda is not None, "a marca não está na faixa dos menus"
    assert direita is janela.brand_context
    # E os cinco menus continuam lá: a faixa GANHOU conteúdo, não trocou.
    assert [a.text() for a in barra.actions()] == [
        "Arquivo", "Editar", "Ferramentas", "Configurações", "Janela"
    ]


def test_o_contexto_mostra_a_biblioteca_e_o_modo(janela, qapp):
    """A contagem de assets, que o mockup punha aqui, já aparece no cabeçalho
    da lista E no rodapé — um terceiro lugar seria ruído. O que não aparece
    em lugar nenhum é qual biblioteca está aberta (são várias desde a F41)."""
    texto = janela.brand_context.text()
    assert janela._library_root.name in texto
    assert ("Escuro" in texto) or ("Claro" in texto)


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


def test_menu_arquivo_reindexar_e_sair_tem_atalho(janela):
    from PySide6.QtGui import QKeySequence

    assert janela.reindex_action.shortcut() == QKeySequence("Ctrl+R")
    assert janela.sair_action.shortcut() == QKeySequence.StandardKey.Quit
    assert janela.reindex_action in janela._menu_arquivo.actions()
    assert janela.sair_action in janela._menu_arquivo.actions()


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
