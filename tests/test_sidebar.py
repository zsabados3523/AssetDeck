"""Barra lateral (Fatia 45): contadores, recolher, rail.

O que estes testes protegem, em ordem de importância:

1. O contador não pode divergir da lista logo abaixo dele. É o motivo de ele
   escutar o modelo da view em vez de ser chamado à mão nos `reload()`.
2. Recolher precisa DEVOLVER altura. Uma seção que fecha mas continua
   ocupando o mesmo espaço no splitter não serve para nada.
3. Rail e menu Janela têm de contar a mesma história. Dois controles para o
   mesmo estado é a receita clássica de um mentir sobre o outro.
"""

import pytest
from PySide6.QtWidgets import QListWidget, QTreeWidget, QTreeWidgetItem

from assetdeck.ui import theme
from assetdeck.ui.sidebar import Sidebar, SidebarSection, contar_itens


@pytest.fixture
def arvore(qapp):
    """Uma view no formato das laterais de verdade: uma linha sintética no
    topo ("(sem filtro)") e os itens reais depois dela."""
    t = QTreeWidget()
    t.setHeaderHidden(True)
    t.addTopLevelItem(QTreeWidgetItem(["(sem filtro)"]))
    return t


def _povoar(arvore, nomes, filhos_de=None):
    for nome in nomes:
        item = QTreeWidgetItem([nome])
        if filhos_de is None:
            arvore.addTopLevelItem(item)
        else:
            filhos_de.addChild(item)
    return arvore


# ------------------------------------------------------------- contagem --

def test_contagem_desconta_a_linha_sintetica(arvore):
    assert contar_itens(arvore) == 0, "só a linha sintética = zero itens reais"
    _povoar(arvore, ["madeira", "metal", "pedra"])
    assert contar_itens(arvore) == 3


def test_contagem_inclui_itens_aninhados(arvore):
    """A árvore de pastas e a de tags têm filhos. Contar só o topo diria
    "5 pastas" numa biblioteca com 50 subpastas."""
    pai = QTreeWidgetItem(["Acabamento"])
    arvore.addTopLevelItem(pai)
    _povoar(arvore, ["Brilhante", "Fosco"], filhos_de=pai)
    assert contar_itens(arvore) == 3  # o pai + os dois filhos


def test_contagem_de_lista(qapp):
    lista = QListWidget()
    lista.addItem("(nenhuma aplicada)")
    lista.addItem("4K sem tag")
    assert contar_itens(lista) == 1


def test_contagem_nunca_e_negativa(qapp):
    """View ainda não carregada tem zero itens — "-1" no cabeçalho seria pior
    do que zero."""
    assert contar_itens(QTreeWidget()) == 0
    assert contar_itens(QListWidget()) == 0


def test_contador_acompanha_a_view_sem_ninguem_chamar(arvore, qapp):
    """O ponto principal da fatia: o número escuta o MODELO.

    As views laterais recarregam a partir de sete pontos diferentes do
    MainWindow; se a recontagem dependesse de ser chamada em cada um, bastaria
    esquecer o oitavo para o cabeçalho passar a mentir.
    """
    secao = SidebarSection("tags", "Tags", arvore)
    assert secao.header.contador.text() == "0"

    _povoar(arvore, ["madeira", "metal"])
    qapp.processEvents()
    assert secao.header.contador.text() == "2"

    arvore.clear()
    qapp.processEvents()
    assert secao.header.contador.text() == "0"


# -------------------------------------------------------------- recolher --

def test_recolher_esconde_a_view_e_devolve_altura(arvore, qapp):
    secao = SidebarSection("tags", "Tags", arvore)
    secao.resize(200, 300)
    secao.show()
    qapp.processEvents()

    assert not secao.is_collapsed()
    assert secao.view.isVisible()
    altura_max_aberta = secao.maximumHeight()

    secao.set_collapsed(True)
    qapp.processEvents()
    assert secao.is_collapsed()
    assert not secao.view.isVisible()
    # Sem travar o teto de altura, o splitter continuaria reservando o espaço
    # da view escondida e recolher não devolveria nada.
    assert secao.maximumHeight() < altura_max_aberta
    assert secao.maximumHeight() >= secao.header.sizeHint().height()

    secao.set_collapsed(False)
    qapp.processEvents()
    assert secao.view.isVisible()
    assert secao.maximumHeight() == altura_max_aberta
    secao.close()


def test_clicar_no_cabecalho_alterna(arvore, qapp):
    secao = SidebarSection("tags", "Tags", arvore)
    secao.header.clicked.emit()
    assert secao.is_collapsed()
    secao.header.clicked.emit()
    assert not secao.is_collapsed()


def test_recolher_duas_vezes_seguidas_nao_faz_nada(arvore, qapp):
    """`set_collapsed(True)` repetido não pode encolher o teto de altura de
    novo em cima do valor já encolhido."""
    secao = SidebarSection("tags", "Tags", arvore)
    secao.set_collapsed(True)
    teto = secao.maximumHeight()
    secao.set_collapsed(True)
    assert secao.maximumHeight() == teto


# ------------------------------------------------------------------ rail --

@pytest.fixture
def lateral(qapp, arvore):
    outra = QTreeWidget()
    outra.setHeaderHidden(True)
    outra.addTopLevelItem(QTreeWidgetItem(["(sem filtro)"]))
    return Sidebar([
        ("pastas", "Pastas", "nav-pastas", arvore),
        ("tags", "Tags", "nav-tags", outra),
    ])


def test_rail_tem_um_botao_por_secao(lateral):
    assert set(lateral.rail.buttons) == {"pastas", "tags"}
    assert all(b.isChecked() for b in lateral.rail.buttons.values())


def test_rail_esconde_e_reexibe_a_secao(lateral, qapp):
    lateral.resize(260, 500)
    lateral.show()
    qapp.processEvents()

    assert lateral.section_widget("tags").isVisible()
    lateral.rail.buttons["tags"].setChecked(False)
    qapp.processEvents()
    assert not lateral.section_widget("tags").isVisible()

    lateral.rail.buttons["tags"].setChecked(True)
    qapp.processEvents()
    assert lateral.section_widget("tags").isVisible()
    lateral.close()


def test_esconder_pela_api_marca_o_rail(lateral):
    """O caminho do menu Janela. Se o rail não acompanhasse, o ícone ficaria
    aceso apontando para uma seção que não está na tela."""
    lateral.set_section_visible("tags", False)
    assert not lateral.rail.buttons["tags"].isChecked()

    lateral.set_section_visible("tags", True)
    assert lateral.rail.buttons["tags"].isChecked()


def test_sincronizar_o_rail_nao_dispara_o_sinal(lateral):
    """Senão vira laço: menu manda esconder → rail remarca → rail avisa o menu
    → menu manda esconder de novo."""
    recebidos = []
    lateral.rail.section_toggled.connect(lambda k, v: recebidos.append((k, v)))
    lateral.set_section_visible("tags", False)
    assert recebidos == []


def test_secao_desconhecida_e_erro_logado_nao_excecao(lateral, caplog):
    """Regra do projeto: nada de `except` silencioso, mas a lateral também não
    pode derrubar a janela por causa de uma chave errada."""
    with caplog.at_level("ERROR"):
        lateral.set_section_visible("nao-existe", False)
        lateral.rail.set_checked("nao-existe", False)
    assert "nao-existe" in caplog.text


def test_a_largura_minima_cabe_o_cabecalho_mais_largo(qapp):
    """Piso derivado do conteúdo, não escolhido a dedo.

    "SMART COLLECTIONS" pede ~219px e o piso antigo era 200: o rótulo saía
    cortado no meio da palavra. Com o piso derivado, renomear uma seção
    reajusta sozinho — e este teste falha se alguém voltar a cravar um número.
    """
    vazia = QTreeWidget()
    vazia.addTopLevelItem(QTreeWidgetItem(["(sem filtro)"]))
    outra = QTreeWidget()
    outra.addTopLevelItem(QTreeWidgetItem(["(sem filtro)"]))

    lateral = Sidebar([
        ("curta", "Tags", "nav-tags", vazia),
        ("longa", "Smart Collections", "nav-smart", outra),
    ])
    maior = lateral.section_widget("longa").header.sizeHint().width()
    assert lateral.minimumWidth() >= maior, "o cabeçalho mais largo não cabe no piso"


def _imagem_do_icone(botao):
    """A IMAGEM do ícone, não o `cacheKey()`.

    `cacheKey()` é por instância de QIcon, e `icons.icon()` devolve um QIcon
    novo a cada chamada — comparar cacheKey acusa "mudou" mesmo quando a cor é
    exatamente a mesma. Estes dois testes usavam cacheKey e passavam sozinhos,
    sem provar que a cor mudava (achado na Fatia 46).
    """
    return botao.icon().pixmap(18, 18).toImage()


def test_o_icone_do_rail_muda_de_cor_com_o_estado(lateral, qapp):
    """O ícone é pintado em Python — se não for retingido, a seção escondida
    fica com o glifo idêntico ao da seção visível."""
    visivel = _imagem_do_icone(lateral.rail.buttons["tags"])

    lateral.set_section_visible("tags", False)
    assert _imagem_do_icone(lateral.rail.buttons["tags"]) != visivel, \
        "o ícone da seção escondida não apagou"

    lateral.set_section_visible("tags", True)
    assert _imagem_do_icone(lateral.rail.buttons["tags"]) == visivel


def test_a_lateral_sobrevive_a_troca_de_modo(lateral, qapp):
    """Widget que pinta cor à mão precisa de `refresh_theme()` — é a armadilha
    já documentada no REDESIGN-V2, e a lateral inteira cai nela (chevron do
    cabeçalho e ícones do rail)."""
    theme.apply_theme(qapp, theme.Variant(mode="escuro"))
    lateral.refresh_theme()
    escuro = _imagem_do_icone(lateral.rail.buttons["pastas"])

    theme.apply_theme(qapp, theme.Variant(mode="claro"))
    lateral.refresh_theme()
    assert _imagem_do_icone(lateral.rail.buttons["pastas"]) != escuro, \
        "o ícone do rail não acompanhou a troca de modo"
