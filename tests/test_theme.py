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


# ------------------------------------------------- destaque azul (F44) --

def test_contraste_do_destaque_sobre_a_pastilha_suave():
    """A pastilha suave (`accent_soft`) é o estado ATIVO de filtro/categoria, e
    o texto dela é o próprio destaque — azul sobre azul lavado.

    É o par mais apertado da paleta inteira: quem escurece o `accent` para ele
    caber melhor sobre branco piora aqui, e vice-versa. Travado nos dois modos
    porque foi calibrado à mão entre os dois limites.
    """
    assert theme.contrast_ratio(theme.ACCENT, theme.ACCENT_SOFT) >= 4.5
    assert theme.contrast_ratio(theme.ACCENT_DARK, theme.ACCENT_SOFT_DARK) >= 4.5


# Quanto dois tons vizinhos precisam diferir para o degrau ser visível.
# Medido em RAZÃO DE CONTRASTE, não em luminância crua: a luminância relativa
# satura perto do preto (o degrau #101114 → #1A1B1F dá 0,003 nela, contra
# 0,077 do degrau equivalente no modo claro) e reprovaria um degrau escuro que
# a tela mostra perfeitamente. A razão de contraste carrega o termo +0,05 da
# WCAG justamente para continuar útil nessa faixa. O piso é o degrau do modo
# claro (#F6F6F9 → #FFFFFF = 1,079), arredondado para baixo.
DEGRAU_MINIMO = 1.07


def test_a_pastilha_suave_se_distingue_da_superficie():
    """`accent_soft` tem de ser VISÍVEL como pastilha: se ficar perto demais da
    superfície, o estado ativo some e voltamos ao problema que o Rafael
    relatou (não dava pra ver qual categoria estava ligada)."""
    for soft, superficie in (
        (theme.ACCENT_SOFT, theme.SURFACE),
        (theme.ACCENT_SOFT_DARK, theme.SURFACE_DARK),
    ):
        razao = theme.contrast_ratio(soft, superficie)
        assert razao >= DEGRAU_MINIMO, f"{soft} não se destaca de {superficie} ({razao:.3f})"


def test_o_painel_se_separa_do_fundo_por_tom_ou_por_contorno():
    """A hierarquia da tela tem de vir de ALGUM lugar.

    A Fatia 44 separou painel e janela por TOM, e este teste exigia que as
    duas cores fossem diferentes. Na Fatia 95 o Rafael pediu fundo branco no
    modo claro — "as janelas já têm sombra e linha, tem contraste" —, e no
    claro os dois passaram a ser o mesmo branco. A exigência antiga não vale
    mais como está escrita, mas o que ela protegia continua valendo: se o tom
    não separa, o contorno tem de separar. Sem nenhum dos dois, volta a tela
    chapada que ele reprovou.

    No escuro os tons continuam diferentes — o pedido era só pro claro.
    """
    for modo, bg, superficie in (("claro", theme.BG, theme.SURFACE),
                                 ("escuro", theme.BG_DARK, theme.SURFACE_DARK)):
        if bg != superficie:
            razao = theme.contrast_ratio(bg, superficie)
            assert razao >= DEGRAU_MINIMO, (
                f"[{modo}] {bg} e {superficie} são degraus fracos ({razao:.3f})")
            continue
        # Mesmo tom: o contorno do card é o único separador que sobra, então
        # ele NÃO pode ser transparente.
        alfa = theme._paleta(modo)["border"][3]
        assert alfa > 0, (
            f"[{modo}] fundo e painel são a mesma cor ({bg}) e o contorno do "
            f"card é transparente — a tela fica chapada")


def test_o_campo_se_distingue_do_painel_nos_dois_modos():
    """O campo de busca some no painel se os dois forem a mesma cor — era o
    caso até a Fatia 43, quando `field` era literalmente `bg`. No claro ele
    afunda em relação ao branco; no escuro, em relação ao painel."""
    for campo, superficie in ((theme.FIELD, theme.SURFACE), (theme.FIELD_DARK, theme.SURFACE_DARK)):
        razao = theme.contrast_ratio(campo, superficie)
        assert razao >= DEGRAU_MINIMO, f"{campo} some em {superficie} ({razao:.3f})"


def test_a_pastilha_de_tipo_nao_usa_a_cor_de_destaque():
    """O card sem miniatura aparece dezenas de vezes ao mesmo tempo na grade.
    Pintá-lo de azul faria da AUSÊNCIA de miniatura o elemento mais gritante da
    tela — por isso `TYPE_TINT` é constante própria e não um apelido de
    `ACCENT`, como já foi."""
    assert theme.TYPE_TINT != theme.ACCENT
    assert theme.TYPE_TINT_DARK != theme.ACCENT_DARK


def test_o_qss_nao_tem_cor_literal(qapp):
    """Regra do projeto: nenhuma cor cravada no theme.qss — tudo entra como
    token no theme.py.

    Não é preciosismo: os três "#FFFFFF" que estavam aqui (fundo do checkbox,
    do indicador de árvore e da alça do slider) atravessaram o modo escuro
    inteiro da Fatia 43 sem ninguém ver, e acendiam confetes brancos numa
    janela quase preta.
    """
    folha = QSS_SEM_TOKENS = re.sub(r"\$\w+", "", _sem_comentarios(_QSS_CRU()))
    literais = re.findall(r"#[0-9A-Fa-f]{3,8}\b", QSS_SEM_TOKENS)
    assert not literais, f"cor literal no theme.qss: {literais} — vire token no theme.py"
    assert folha  # a folha não pode estar vazia (senão o teste passa à toa)


def _QSS_CRU() -> str:
    """O theme.qss ANTES da substituição — é nele que a cor literal apareceria.
    Depois de substituído, todo token vira hex e o teste não distinguiria."""
    return theme.QSS_FILE.read_text(encoding="utf-8")


# ------------------------------------------------------ modo escuro (F43) --

@pytest.mark.parametrize("separation", list(theme.SEPARATION))
def test_contraste_do_texto_sobre_o_painel_escuro(separation):
    """Mesma régua do modo claro (WCAG, pedido do Rafael) — só a paleta
    escura precisa passar no mesmo mínimo, luminância invertida."""
    variant = theme.Variant(separation=separation, mode="escuro")
    superficie = theme.surface_solid(variant)
    assert theme.contrast_ratio(theme.TEXT_DARK, superficie) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_MUTED_DARK, superficie) >= 3.0
    assert theme.contrast_ratio(theme.WARNING_DARK, superficie) >= 4.5
    assert theme.contrast_ratio(theme.DANGER_DARK, superficie) >= 4.5
    assert theme.contrast_ratio(theme.ACCENT_DARK, superficie) >= 4.5


@pytest.mark.parametrize("separation", list(theme.SEPARATION))
def test_contraste_do_texto_selecionado_escuro(separation):
    """Seleção no escuro é branco translúcido sobre o fundo escuro (o
    inverso do preto translúcido sobre fundo claro) — mesma legibilidade
    mínima."""
    variant = theme.Variant(separation=separation, mode="escuro")
    pastilha = theme.blend(theme.SELECTION_DARK, theme.surface_solid(variant))
    assert theme.contrast_ratio(theme.TEXT_DARK, pastilha) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_MUTED_DARK, pastilha) >= 3.0


def test_contraste_do_texto_sobre_o_destaque_e_sobre_o_popup_escuro():
    assert theme.contrast_ratio(theme.ON_ACCENT_DARK, theme.ACCENT_DARK) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_DARK, theme.POPOVER_DARK) >= 4.5
    assert theme.contrast_ratio(theme.TEXT_DARK, theme.BG_DARK) >= 4.5


def test_contraste_do_rotulo_sobre_o_card_sem_miniatura_escuro():
    assert theme.contrast_ratio(theme.ON_TYPE_TINT_DARK, theme.TYPE_TINT_DARK) >= 4.5


def test_apply_theme_no_modo_escuro_nao_lanca_key_error(qapp):
    """`build_qss`/`Template.substitute` são estritos de propósito — token
    faltando levanta na hora. Roda os dois modos pra pegar qualquer token
    de cor que eu tenha esquecido de mapear em `_paleta()`."""
    theme.apply_theme(qapp, theme.Variant(mode="escuro"))
    theme.apply_theme(qapp, theme.Variant(mode="claro"))  # devolve pro padrão


def test_current_colors_reflete_o_ultimo_apply_theme(qapp):
    theme.apply_theme(qapp, theme.Variant(mode="escuro"))
    assert theme.current_colors()["bg"] == theme.BG_DARK

    theme.apply_theme(qapp, theme.Variant(mode="claro"))
    assert theme.current_colors()["bg"] == theme.BG


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


def test_o_card_pinta_a_superficie_mesmo_nao_sendo_um_qframe(qapp):
    """Regressão da Fatia 49, relatada pelo Rafael como "sombras bugadas".

    O seletor era `QFrame#card`. O DetailsPanel é uma subclasse de QWidget com
    objectName "card" — a regra nunca casou com ele e o painel ficou
    TRANSPARENTE desde a Fatia 25. Ninguém percebeu porque fundo e superfície
    eram o mesmo branco; quando a Fatia 44 separou os dois, o painel passou a
    mostrar o fundo da janela e pareceu um defeito de sombra.

    Este teste usa um QWidget de propósito: com `QFrame#card` de volta, ele
    falha; com `#card`, passa.
    """
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    hospedeiro = QWidget()
    hospedeiro.setAttribute(_Qt.WidgetAttribute.WA_StyledBackground, True)
    hospedeiro.setObjectName("appSurface")
    layout = QVBoxLayout(hospedeiro)
    layout.setContentsMargins(20, 20, 20, 20)

    painel = QWidget()  # QWidget, NÃO QFrame — é este o caso que quebrava
    painel.setAttribute(_Qt.WidgetAttribute.WA_StyledBackground, True)
    painel.setObjectName("card")
    layout.addWidget(painel)

    hospedeiro.resize(300, 300)
    hospedeiro.setStyleSheet(theme.build_qss())
    hospedeiro.show()
    qapp.processEvents()

    img = hospedeiro.grab().toImage()
    meio = QColor(img.pixelColor(150, 150)).name().upper()
    assert meio == theme.SURFACE.upper(), (
        f"widget #card não pintou a superfície (leu {meio})"
    )
    hospedeiro.close()


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


def test_scroll_area_do_painel_de_detalhes_nao_cobre_os_cantos(qapp):
    """Bug visto na tela: o painel de detalhes (que é ele mesmo um #card,
    Fatia 25) rola o conteúdo por dentro desde a Fatia 28c — mas o viewport
    de uma QScrollArea preenche o PRÓPRIO fundo por padrão (branco opaco),
    cobrindo os cantos arredondados do #card por baixo. O painel inteiro
    parecia quadrado.

    Não dá pra provar isto por pixel de forma confiável neste ambiente (o
    tema é branco sobre branco por design — "Craft style" — e o
    QGraphicsDropShadowEffect não renderiza sob QT_QPA_PLATFORM=offscreen).
    A prova aqui é de configuração: o viewport não pode se autopreencher.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QFrame, QScrollArea

    from assetdeck.ui.details_panel import DetailsPanel

    dp = DetailsPanel(Path("/tmp"))
    scroll = dp.findChild(QScrollArea)
    assert scroll is not None, "o painel de detalhes precisa rolar por dentro"
    assert scroll.frameShape() == QFrame.Shape.NoFrame
    assert scroll.viewport().autoFillBackground() is False


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


def test_mascara_de_cantos_nao_quebra_menu_e_dialogo_fica_quadrado(tema_isolado):
    """`install_popup_corner_mask` (aplicado por `apply_theme`) não pode
    lançar exceção ao mostrar um QMenu — e o QSS continua sendo pintado por
    baixo da máscara (o offscreen recusa `setMask()` de verdade, então isto
    é o que dá pra provar automatizado; o corte em si só é verificável na
    tela real).

    QDialog é testado aqui também, mas para o oposto: ele NÃO pode ter
    `border-radius` nem entrar na máscara. Foi tentado e revertido — um
    QDialog ganha barra de título nativa do gerenciador de janelas, e
    cortar cantos por baixo dela deixava uma costura feia (visto na tela
    pelo Rafael)."""
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


def test_qdialog_nao_arredonda(tema_isolado):
    theme.apply_theme(tema_isolado)
    qss_dialog = [b for b in theme.build_qss().split("}") if "QDialog {" in b][0]
    assert "border-radius" not in qss_dialog
    assert "border:" not in qss_dialog


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

    assert set(janela._combos) == {"background", "separation", "radius", "font", "mode"}
    assert "contraste" in janela.rodape.text()

    janela._combos["separation"].setCurrentIndex(2)  # dispara o reaplicar
    tema_isolado.processEvents()
    assert janela.variant.separation == "forte"
    janela.close()


# ------------------------------------------------- botão principal apagado --

@pytest.mark.parametrize("modo", ["claro", "escuro"])
def test_botao_principal_desabilitado_nao_fica_com_a_cor_de_destaque(qapp, modo):
    """Regressão da Fatia 74 (achada na revisão visual da Fase 7).

    `QPushButton#primary` é seletor de ID e ganha de `QPushButton:disabled`
    (pseudo-classe) na especificidade do QSS. Sem uma regra `#primary:disabled`
    própria, o botão principal continuava pintado com a cor de destaque mesmo
    desligado — no painel de detalhes, sem asset selecionado, "Abrir com app
    padrão" parecia clicável ao lado de um "Abrir pasta" corretamente apagado.

    O teste PINTA o botão de verdade e lê o pixel do miolo, em vez de procurar
    o seletor no texto do QSS: o que importa é a cor que chega na tela, não a
    regra existir.
    """
    from PySide6.QtWidgets import QPushButton

    variante = theme.Variant(mode=modo)
    destaque = theme._paleta(modo)["accent"].upper()

    botao = QPushButton("Abrir com app padrão")
    botao.setObjectName("primary")
    botao.setStyleSheet(theme.build_qss(variante))
    botao.resize(220, 40)
    botao.setEnabled(False)
    botao.show()
    qapp.processEvents()

    meio = _pixel(botao.grab().toImage(), 110, 20)
    botao.close()

    assert meio != destaque, (
        f"o botão principal DESABILITADO ainda está pintado com o destaque "
        f"({destaque}) no modo {modo}"
    )


# ------------------------------------------- degraus de elevação (F75) --

@pytest.mark.parametrize("modo", ["claro", "escuro"])
def test_o_degrau_de_elevacao_e_visivel_sobre_a_superficie(modo):
    """Hover que ninguém enxerga não é feedback.

    Até a Fatia 75 todo controle do app usava `$surface_hover` — o véu de
    3,5% de preto —, e o Rafael relatou que a interface parecia não responder
    ao mouse. `surface_raised`/`surface_sunken` são degraus de verdade a
    partir de `surface`, e este teste trava isso: se alguém amaciar os tons
    de novo até virarem invisíveis, falha aqui.
    """
    pal = theme._paleta(modo)
    superficie = pal["surface"]

    for nome in ("surface_raised", "surface_sunken"):
        razao = theme.contrast_ratio(pal[nome], superficie)
        assert razao >= DEGRAU_MINIMO, (
            f"{nome} ({pal[nome]}) não se distingue de surface ({superficie}) "
            f"no modo {modo}: {razao:.3f}"
        )

    # "Afundado" tem de ser MAIS marcado que "levantado" — é o clique, o
    # estado mais forte dos dois. Vale nos dois modos, mesmo eles andando em
    # direções opostas (o claro escurece, o escuro clareia).
    assert (
        theme.contrast_ratio(pal["surface_sunken"], superficie)
        > theme.contrast_ratio(pal["surface_raised"], superficie)
    ), f"o clique não é mais marcado que o hover no modo {modo}"


def _seletores(qss: str) -> list[str]:
    """Todos os seletores da folha, um por regra (sem os comentários)."""
    limpo = _sem_comentarios(qss)
    return [bloco.split("}")[-1].strip() for bloco in limpo.split("{")[:-1]]


def test_todo_botao_com_hover_por_id_tambem_define_pressed(qapp):
    """Armadilha de especificidade do QSS — já mordeu duas vezes (Fatia 74 e
    75).

    `QPushButton#ghost` é seletor de ID e ganha de `QPushButton:pressed`
    (pseudo-classe). Então um botão com regra por ID NÃO herda o estado de
    clique genérico: ele fica parado no hover enquanto está sendo apertado,
    sem sinal nenhum de que o clique pegou. Toda regra de botão por ID que
    define `:hover` tem de definir `:pressed` também.
    """
    qss = theme.build_qss()
    seletores = _seletores(qss)

    def alvos(sufixo: str) -> set[str]:
        achados = set()
        for seletor in seletores:
            for parte in seletor.split(","):
                parte = parte.strip()
                if "#" not in parte or not parte.endswith(sufixo):
                    continue
                if "QPushButton" not in parte and "QToolButton" not in parte:
                    continue
                achados.add(parte[: -len(sufixo)])
        return achados

    com_hover = alvos(":hover")
    com_pressed = alvos(":pressed")

    faltando = com_hover - com_pressed
    assert not faltando, (
        "estes botões têm :hover por ID mas nenhum :pressed — o clique some "
        f"por especificidade: {sorted(faltando)}"
    )


# --------------------------------------------------- pastilha (Fatia 76) --

@pytest.mark.parametrize("fonte", list(theme.FONTS))
def test_o_raio_da_pastilha_cabe_na_altura_do_botao(qapp, fonte, tmp_path):
    """Armadilha do Qt que só aparece na tela: quando `border-radius` passa
    de METADE da altura do widget, o Qt **descarta a regra inteira** em vez
    de cortar o raio — o botão volta a ser um retângulo, sem erro nenhum.

    A 1ª tentativa desta fatia usou `999px` de propósito ("o Qt corta"), e o
    resultado foi botão quadrado na tela. Também não adianta `50%`: o Qt
    ignora. Como a altura do botão depende da FONTE, o teste roda pra cada
    uma — se alguma encolher os botões a ponto de 18px passar da metade, as
    pastilhas de categoria/filtro silenciosamente viram retângulos.
    """
    from assetdeck.db.connection import connect
    from assetdeck.db.migrate import apply_migrations
    from assetdeck.ui.categories import CATEGORIES
    from assetdeck.ui.category_bar import CategoryButton
    from assetdeck.ui.filter_button import FilterButton
    from assetdeck.ui.library_switcher import LibrarySwitcher
    from assetdeck.ui.main_window import PALETA_CORES

    theme.apply_theme(qapp, theme.Variant(font=fonte))
    tokens = theme.build_tokens(theme.Variant(font=fonte))

    def raio_de(token: str) -> int:
        return int(tokens[token].removesuffix("px"))

    from pathlib import Path

    conn = connect(Path(tmp_path) / "t.db")
    apply_migrations(conn)

    botoes = [
        ("CategoryButton", CategoryButton(CATEGORIES[0]), "radius_pill"),
        ("FilterButton", FilterButton("palette", PALETA_CORES, swatch=True), "radius_pill"),
        # O seletor de biblioteca entrou aqui DEPOIS de escapar: ele usa o
        # mesmo `$radius_pill`, mas tinha padding próprio e menor, então
        # media 31px — abaixo do dobro do raio. O Qt descartou o
        # arredondamento em silêncio e o botão ficou quadrado na tela até o
        # Rafael reclamar. Um teste que cobre só dois dos três usuários do
        # token não protege o token.
        # O seletor encolheu na Fatia 95 (pedido do Rafael: ele ocupava a
        # faixa inteira e não tinha como parecer centralizado), então passou a
        # usar um token de raio PRÓPRIO — 18px não caberia mais nos 26px de
        # altura. Cada botão é conferido contra o token QUE ELE USA: um teste
        # que cobrisse todos contra o mesmo token voltaria a mentir na
        # primeira vez que um deles mudasse de tamanho.
        ("LibrarySwitcher", LibrarySwitcher(conn, 1), "radius_pill_small"),
    ]
    for nome, b, token in botoes:
        b.show()
        qapp.processEvents()
        altura = b.sizeHint().height()
        raio = raio_de(token)
        assert raio <= altura / 2, (
            f"{nome} (fonte {fonte}) tem {altura}px de altura; um raio de "
            f"{raio}px (${token}) passa da metade e o Qt descarta o "
            f"arredondamento"
        )
        b.close()
