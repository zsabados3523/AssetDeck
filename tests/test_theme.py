"""Tema visual (F4, Fatia 24): tokens, QSS, contraste e o fundo com grão.

O teste mais importante aqui é o de PIXEL: o Qt descarta em silêncio uma regra
de QSS com erro de sintaxe, então conferir que a folha "gerou sem exceção" não
prova nada. Só pintar o widget e ler a cor do pixel prova.
"""

import re

import pytest

from assetdeck.ui import theme


# ---------------------------------------------------------------- tokens --

def test_variant_recusa_valor_invalido():
    with pytest.raises(ValueError, match="separation"):
        theme.Variant(separation="altissima")


def _sem_comentarios(qss: str) -> str:
    """Só as regras. Os comentários do theme.qss falam de tokens e de seletores
    proibidos, e confundiriam as buscas dos testes abaixo."""
    return re.sub(r"/\*.*?\*/", "", qss, flags=re.DOTALL)


@pytest.mark.parametrize("variant", [
    theme.Variant(),
    theme.Variant(separation="sutil", radius="marcante"),
    theme.Variant(separation="forte", font="sistema"),
])
def test_qss_nao_deixa_token_sem_substituir(qapp, variant):
    regras = _sem_comentarios(theme.build_qss(variant))
    assert "$" not in regras, "sobrou um token no QSS gerado"
    assert regras.count("{") == regras.count("}")


def test_token_inexistente_no_qss_explode(qapp, tmp_path, monkeypatch):
    """Token errado tem de falhar alto, não vazar '$nome' para dentro do QSS."""
    falso = tmp_path / "theme.qss"
    falso.write_text("QWidget { color: $cor_que_nao_existe; }", encoding="utf-8")
    monkeypatch.setattr(theme, "QSS_FILE", falso)
    with pytest.raises(KeyError):
        theme.build_qss()


def test_qss_ausente_da_erro_claro(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "QSS_FILE", tmp_path / "nao_existe.qss")
    with pytest.raises(FileNotFoundError):
        theme.build_qss()


def test_qss_nao_estiliza_item_da_grade(qapp):
    """Regra de performance: `QListView::item` joga a pintura da grade para o
    QStyleSheetStyle item a item e mata a rolagem com centenas de assets."""
    assert "QListView::item" not in _sem_comentarios(theme.build_qss())


def test_todo_url_do_qss_aponta_para_arquivo_existente(qapp):
    for variant in (theme.Variant(background="liso"), theme.Variant(background="grao")):
        qss = theme.build_qss(variant)
        for caminho in re.findall(r"url\(([^)]+)\)", qss):
            alvo = caminho.strip().strip("'\"")
            from pathlib import Path
            assert Path(alvo).is_absolute(), f"url() relativo não resolve no Qt: {alvo}"
            assert Path(alvo).exists(), f"url() aponta para arquivo inexistente: {alvo}"


# ------------------------------------------------------------------- cor --

def test_blend_compoe_como_o_qt():
    assert theme.blend((255, 255, 255, 1.0), "#000000") == "#FFFFFF"
    assert theme.blend((255, 255, 255, 0.0), "#000000") == "#000000"
    assert theme.blend((255, 255, 255, 0.5), "#000000") == "#808080"


def test_luminancia_nos_extremos():
    assert theme.relative_luminance("#FFFFFF") == pytest.approx(1.0, abs=1e-6)
    assert theme.relative_luminance("#000000") == pytest.approx(0.0, abs=1e-6)
    assert theme.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=1e-6)


def test_hex_invalido_da_erro():
    with pytest.raises(ValueError):
        theme.hex_to_rgb("#ABC")


@pytest.mark.parametrize("separation", list(theme.SEPARATION))
def test_contraste_do_texto_sobre_o_painel(separation):
    """Legibilidade foi pedido explícito do Rafael — isto não é enfeite.

    Mede contra a cor OPACA equivalente ao painel translúcido sobre o fundo,
    que é o que a tela realmente mostra.
    """
    superficie = theme.surface_solid(theme.Variant(separation=separation))
    assert theme.contrast_ratio(theme.TEXT, superficie) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_MUTED, superficie) >= 3.0
    assert theme.contrast_ratio(theme.WARNING, superficie) >= 4.5
    assert theme.contrast_ratio(theme.DANGER, superficie) >= 4.5
    assert theme.contrast_ratio(theme.ACCENT, superficie) >= 4.5


@pytest.mark.parametrize("separation", list(theme.SEPARATION))
def test_contraste_do_texto_selecionado(separation):
    """A seleção é monocromática: pastilha de cinza claro, texto normal.

    Sem cor para sinalizar o estado, a legibilidade do texto sobre a pastilha
    é a única coisa que sobra — então ela é travada aqui.
    """
    variant = theme.Variant(separation=separation)
    pastilha = theme.blend(theme.SELECTION, theme.surface_solid(variant))
    assert theme.contrast_ratio(theme.TEXT, pastilha) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_MUTED, pastilha) >= 3.0


def test_contraste_do_texto_sobre_o_destaque_e_sobre_o_popup():
    assert theme.contrast_ratio(theme.ON_ACCENT, theme.ACCENT) >= 4.5
    assert theme.contrast_ratio(theme.TEXT, theme.POPOVER) >= 4.5
    assert theme.contrast_ratio(theme.TEXT, theme.BG) >= 4.5


def test_contraste_do_rotulo_sobre_o_card_sem_miniatura():
    """Não há mais cor por tipo — uma pastilha cinza só (TYPE_TINT)."""
    assert theme.contrast_ratio(theme.ON_TYPE_TINT, theme.TYPE_TINT) >= 4.5


# ---------------------------------------------------------- fundo (grão) --

def test_fundo_liso_nao_gera_ladrilho():
    assert theme.background_tile_path(theme.Variant(background="liso")) is None


def test_ladrilho_do_grao_e_gerado_e_reaproveitado(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path))
    variant = theme.Variant(background="grao")

    caminho = theme.background_tile_path(variant)
    assert caminho is not None and caminho.exists()
    assert caminho.stat().st_size > 0

    # Segunda chamada reaproveita o arquivo em vez de gerar de novo.
    marca = caminho.stat().st_mtime_ns
    assert theme.background_tile_path(variant) == caminho
    assert caminho.stat().st_mtime_ns == marca

    from PySide6.QtGui import QImage
    img = QImage(str(caminho))
    assert (img.width(), img.height()) == (theme.TILE, theme.TILE)


# ----------------------------------------------------------- pixel / Qt --

@pytest.fixture
def sonda(qapp):
    """Widget-sonda: fundo + card, pintados só com o QSS do tema.

    O QSS é aplicado no próprio widget (não em `QApplication`) de propósito —
    stylesheet global vazaria para os outros testes de UI da suíte.
    """
    from PySide6.QtWidgets import QLabel, QWidget
    from PySide6.QtCore import Qt

    raiz = QWidget()
    raiz.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    raiz.setObjectName("appSurface")
    raiz.resize(400, 300)

    card = theme.make_card(QLabel("conteúdo"), sombra=False)
    card.setParent(raiz)
    card.setGeometry(50, 50, 300, 200)

    yield raiz
    raiz.close()


def _pixel(imagem, x, y) -> str:
    from PySide6.QtGui import QColor
    return QColor(imagem.pixelColor(x, y)).name(QColor.NameFormat.HexRgb).upper()


def _borda_do_card(sonda) -> str:
    """Pixel do meio da aresta esquerda do card (x=50, y=150 na sonda)."""
    return _pixel(sonda.grab().toImage(), 50, 150)


def test_checkbox_de_arvore_nao_fica_preto(qapp):
    """Bug visto na tela (tags_tree do painel de detalhes): sem uma regra
    própria para QTreeView::indicator, o Qt desenha o checkbox de item de
    árvore/lista como um quadrado PRETO sólido assim que qualquer stylesheet
    global está ativo — marcado ou não, ilegível dos dois jeitos."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

    raiz = QWidget()
    raiz.setAttribute(_Qt.WidgetAttribute.WA_StyledBackground, True)
    raiz.setObjectName("appSurface")
    raiz.resize(200, 60)
    raiz.setStyleSheet(theme.build_qss())

    arvore = QTreeWidget(raiz)
    arvore.setGeometry(0, 0, 200, 60)
    arvore.setHeaderHidden(True)
    item = QTreeWidgetItem(["madeira"])
    item.setFlags(item.flags() | _Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(0, _Qt.CheckState.Unchecked)
    arvore.addTopLevelItem(item)

    raiz.show()
    qapp.processEvents()
    img = raiz.grab().toImage()

    pretos = sum(
        1 for x in range(20) for y in range(20)
        if QColor(img.pixelColor(x, y)).name() == "#000000"
    )
    assert pretos == 0, "o indicador da árvore ainda está pintando preto sólido"


def test_o_qss_realmente_pinta_o_card(sonda):
    """Fundo e painel são os dois brancos: o que prova que a folha pegou é a
    LINHA de contorno. Se o Qt descartar o QSS por erro de sintaxe, a aresta
    fica branca igual ao resto."""
    sonda.setStyleSheet(theme.build_qss())
    img = sonda.grab().toImage()

    assert _pixel(img, 10, 10) == theme.BG.upper()          # fundo
    assert _pixel(img, 200, 150) == theme.surface_solid().upper()  # miolo do card
    assert _borda_do_card(sonda) != theme.BG.upper(), "a linha do card não pintou"


def test_o_canto_do_card_e_arredondado(sonda):
    """Regressão do cantos-arredondados-que-vazam.

    Prova a curvatura comparando dois pontos da MESMA aresta: na quina o
    contorno ainda não começou (fundo puro), no meio da aresta ele existe.
    Uma view arredondada sem o QFrame em volta pinta retângulo e falha aqui.
    """
    sonda.setStyleSheet(theme.build_qss())
    img = sonda.grab().toImage()

    assert _pixel(img, 50, 50) == theme.BG.upper(), "a quina do card não é curva"
    assert _pixel(img, 50, 150) != theme.BG.upper()


def test_separacao_controla_o_quanto_a_linha_aparece(sonda):
    """Os três níveis do seletor "Separação" têm de diferir na tela."""
    lidos = []
    for nivel in ("sutil", "media", "forte"):
        sonda.setStyleSheet(theme.build_qss(theme.Variant(separation=nivel)))
        lidos.append(_borda_do_card(sonda))

    assert len(set(lidos)) == 3, f"os três níveis deveriam diferir: {lidos}"
    # Mais separação = linha mais escura.
    claridades = [theme.relative_luminance(c) for c in lidos]
    assert claridades == sorted(claridades, reverse=True)


@pytest.fixture
def tema_isolado(qapp):
    """`apply_theme` mexe na QApplication inteira, que é de sessão.

    Sem restaurar, o tema vazaria para test_main_window/test_grid_state e
    mudaria a geometria que eles conferem.
    """
    antes = (qapp.styleSheet(), qapp.palette(), qapp.font())
    yield qapp
    qss, paleta, fonte = antes
    qapp.setStyleSheet(qss)
    qapp.setPalette(paleta)
    qapp.setFont(fonte)


def test_mascara_de_cantos_nao_quebra_menu_nem_dialogo(tema_isolado):
    """`install_popup_corner_mask` (aplicado por `apply_theme`) não pode
    lançar exceção ao mostrar um QMenu/QDialog — e o QSS continua sendo
    pintado por baixo da máscara (o offscreen recusa `setMask()` de verdade,
    então isto é o que dá pra provar automatizado; o corte em si só é
    verificável na tela real, ver REDESIGN.md)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QDialog, QMenu

    theme.apply_theme(tema_isolado)

    dialogo = QDialog()
    dialogo.resize(200, 120)
    dialogo.show()
    tema_isolado.processEvents()
    img = dialogo.grab().toImage()
    assert QColor(img.pixelColor(100, 60)).name().upper() == theme.BG.upper()
    dialogo.close()

    menu = QMenu()
    menu.addAction("Item de teste")
    menu.popup(dialogo.mapToGlobal(dialogo.rect().center()))
    tema_isolado.processEvents()
    menu.close()  # não travou, não lançou exceção


def test_apply_theme_configura_o_app(tema_isolado):
    from PySide6.QtGui import QFontDatabase

    qapp = tema_isolado
    theme.apply_theme(qapp)

    assert qapp.styleSheet(), "o QSS não chegou na aplicação"
    assert qapp.palette().color(qapp.palette().ColorRole.Highlight).name().upper() \
        == theme.ACCENT.upper()
    # Com stylesheet ativo o Qt embrulha o estilo num QStyleSheetStyle e o
    # nome do estilo-base deixa de ser legível — então o que dá para afirmar é
    # que a folha está no comando e que o Fusion (que apply_theme fixa) existe.
    from PySide6.QtWidgets import QStyleFactory
    assert qapp.style().metaObject().className() == "QStyleSheetStyle"
    assert QStyleFactory.create("Fusion") is not None

    # A fonte só é trocada se estiver instalada — em máquina sem Inter o app
    # tem de seguir com a do sistema, sem quebrar.
    if theme.FONTS["inter"] in QFontDatabase.families():
        assert qapp.font().family() == theme.FONTS["inter"]


def test_todas_as_variantes_aplicam_sem_erro(tema_isolado, tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path))
    for fundo in theme.BACKGROUNDS:
        for nivel in theme.SEPARATION:
            for raio in theme.RADII:
                for fonte in theme.FONTS:
                    theme.apply_theme(tema_isolado, theme.Variant(fundo, nivel, raio, fonte))


# ---------------------------------------------------------------- vitrine --

def test_vitrine_abre_com_as_amostras(tema_isolado):
    from assetdeck.ui.theme_gallery import ThemeGallery

    janela = ThemeGallery()
    janela.show()
    tema_isolado.processEvents()

    assert set(janela._combos) == {"background", "separation", "radius", "font"}
    assert "contraste" in janela.rodape.text()

    janela._combos["separation"].setCurrentIndex(2)  # dispara o reaplicar
    tema_isolado.processEvents()
    assert janela.variant.separation == "forte"
    janela.close()
