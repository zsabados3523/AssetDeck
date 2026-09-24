"""DetailsPanel: botão "Checar texturas…" (Fatia 40) — só aparece pra
asset .blend presente (não sumido)."""

from pathlib import Path

import pytest

from assetdeck.ui.details_panel import DetailsPanel

ROOT = Path("/lib")


def _row(rel_path: str, missing_since=None, asset_id: int = 1) -> dict:
    return {
        "id": asset_id, "name": Path(rel_path).stem, "asset_type": "model",
        "rel_path": rel_path, "size_bytes": 1024, "notes": None,
        "missing_since": missing_since,
    }


@pytest.fixture
def painel(qapp):
    return DetailsPanel(ROOT)


def test_comeca_escondido(painel):
    # isHidden() (não isVisible()): a janela do teste nunca é mostrada de
    # verdade, e isVisible() dependeria da hierarquia toda estar na tela.
    assert painel.check_textures_btn.isHidden() is True


def test_aparece_para_blend_presente(painel):
    painel.show_asset(_row("modelo.blend"), None)
    assert painel.check_textures_btn.isHidden() is False


@pytest.mark.parametrize("rel_path", ["textura.jpg", "modelo.fbx", "projeto.rvt",
                                      "cena.usdz", "peca.abc"])
def test_some_para_outros_formatos(painel, rel_path):
    """Fatia 37: os formatos novos (.rvt/.usd*/.abc) não são arquivos
    Blender — o conceito de textura religável por caminho interno não
    se aplica a eles."""
    painel.show_asset(_row(rel_path), None)
    assert painel.check_textures_btn.isHidden() is True


def test_some_para_blend_sumido(painel):
    painel.show_asset(_row("modelo.blend", missing_since="2026-01-01"), None)
    assert painel.check_textures_btn.isHidden() is True


def test_clicar_emite_o_sinal_com_asset_id_e_caminho(painel):
    recebidos = []
    painel.check_textures_requested.connect(lambda *a: recebidos.append(a))
    painel.show_asset(_row("modelo.blend", asset_id=42), None)

    painel._request_check_textures()

    assert recebidos == [(42, str(ROOT / "modelo.blend"))]


def test_troca_de_blend_pra_outro_formato_esconde_de_novo(painel):
    painel.show_asset(_row("modelo.blend"), None)
    assert painel.check_textures_btn.isHidden() is False

    painel.show_asset(_row("textura.jpg"), None)
    assert painel.check_textures_btn.isHidden() is True


# ------------------------------------------------- layout do painel (F48) --

def test_a_moldura_da_miniatura_existe_mesmo_vazia(painel):
    """Sem asset selecionado, o topo do painel era um buraco de 200px com um
    texto boiando no meio e nada indicando que ali é o lugar da imagem."""
    assert painel.preview.objectName() == "previewTile"
    assert painel.preview.minimumHeight() >= 180


def test_a_ficha_tecnica_alinha_os_valores_a_direita(painel):
    """O QFormLayout deixava o valor começar logo depois do rótulo mais longo:
    linhas com o valor em posições diferentes, impossíveis de varrer com o
    olho. Alinhados à direita, viram uma coluna só.

    Desde a Fatia 79 (mockup aprovado pelo Rafael) sobraram só DOIS campos
    aqui — os que são de fato longos. Tipo, formato e tamanho viraram
    pastilhas no topo, ver o teste logo abaixo.
    """
    from PySide6.QtCore import Qt

    for campo in (painel.f_dims, painel.f_path):
        assert campo.objectName() == "kvValue"
        assert campo.alignment() & Qt.AlignmentFlag.AlignRight


def test_formato_tipo_e_tamanho_sao_pastilhas_no_topo(painel):
    """Fatia 79: eram três das cinco linhas da ficha técnica — respostas
    curtas demais pra ocupar uma linha inteira cada. Viraram chips na altura
    do nome, com o FORMATO em destaque (é o que se procura primeiro)."""
    assert painel.f_format.objectName() == "chipForte"
    assert painel.f_type.objectName() == "chip"
    assert painel.f_size.objectName() == "chip"


def test_tipo_no_detalhe_usa_rotulo_amigavel(painel):
    painel.show_asset(_row("material.blend"), None)
    assert painel.f_type.text() == "Modelo 3D"


def test_as_secoes_do_painel_abrem_e_fecham(painel):
    """O painel empilhava seis blocos sempre abertos — a rolagem passava de
    duas telas. Agora cada um abre e fecha."""
    assert painel.sec_ficha.esta_aberta() is True
    assert painel.sec_tags.esta_aberta() is True
    # As menos usadas nascem fechadas.
    assert painel.sec_galeria.esta_aberta() is False
    assert painel.sec_notas.esta_aberta() is False

    painel.sec_notas.set_aberta(True)
    assert painel.sec_notas.esta_aberta() is True
    assert painel.sec_notas.corpo.isVisibleTo(painel) is True


def test_o_estado_das_secoes_sobrevive_ao_ciclo_de_salvar_e_restaurar(painel):
    """Fechar uma seção só ajuda se ela continuar fechada amanhã — por isso
    o estado vai pro `ui_state` junto do resto do layout."""
    painel.sec_ficha.set_aberta(False)
    painel.sec_galeria.set_aberta(True)
    estado = painel.secoes_expandidas()

    # simula a próxima abertura do app: painel novo, estado restaurado
    outro = type(painel)(painel._root)
    outro.restaurar_secoes(estado)

    assert outro.sec_ficha.esta_aberta() is False
    assert outro.sec_galeria.esta_aberta() is True


def test_chave_desconhecida_no_estado_nao_derruba_a_restauracao(painel):
    """Seção renomeada ou removida numa versão futura não pode impedir o
    resto do layout de voltar."""
    painel.restaurar_secoes({"secao_que_nao_existe": True, "notas": True})
    assert painel.sec_notas.esta_aberta() is True


def test_so_existe_um_botao_principal_no_painel(painel):
    """Regra do tema: um botão principal por tela é o que dá hierarquia. Se
    aparecer um segundo, os dois deixam de significar "é por aqui"."""
    from PySide6.QtWidgets import QPushButton

    principais = [b for b in painel.findChildren(QPushButton)
                  if b.objectName() == "primary"]
    assert len(principais) == 1
    assert principais[0] is painel.open_file_btn


def test_o_favorito_cabe_na_largura_do_painel(painel, qapp):
    """Bug visto na tela (Fatia 9): o favorito dividia a linha com as cinco
    estrelas de nota e era cortado pela borda direita. A nota saiu de vez
    na Fatia 62 (só favorito ficou) — o teste continua garantindo que o
    botão cabe no painel."""
    painel.resize(300, 700)
    painel.show()
    qapp.processEvents()

    direita_do_fav = painel.fav_btn.mapTo(painel, painel.fav_btn.rect().topRight()).x()
    assert direita_do_fav <= painel.width(), "o botão Favorito sai do painel"
    painel.close()


def test_o_tipo_aparece_com_rotulo_especifico_da_tela(painel):
    """"hdri"/"pbr_set" são vocabulário de SCHEMA, não de tela — apareciam em
    minúsculas na ficha técnica. O detalhe usa o mesmo rótulo específico do
    subtítulo do card; tipo desconhecido cai no valor cru em vez de sumir."""
    painel.show_asset(dict(_row("ceu.exr"), asset_type="hdri"), None)
    assert painel.f_type.text() == "HDRI"

    painel.show_asset(dict(_row("parede.blend"), asset_type="pbr_set"), None)
    assert painel.f_type.text() == "Material PBR"

    painel.show_asset(dict(_row("x.zzz"), asset_type="tipo_novo"), None)
    assert painel.f_type.text() == "tipo_novo"


# ------------------------------- largura do painel (Fatia 82) --

def test_nome_e_caminho_longos_nao_alargam_o_painel(painel, qapp):
    """Regressão do que o Rafael relatou: "a janela de detalhes está toda
    ferrada... não aparece por completo".

    Um `QLabel` comum deixa o CONTEÚDO ditar a largura mínima do layout —
    com `wordWrap` ela vira a maior PALAVRA, sem `wordWrap` vira a linha
    inteira. Os nomes da biblioteca dele são tokens sem espaço, então o
    nome exigia 349px e o caminho 284px num painel cujo miolo tem 272px: o
    conteúdo saía 89px mais largo e era cortado.

    O número aqui é o do painel, não o do texto: o rótulo pode desenhar o
    que quiser, desde que não OBRIGUE o painel a crescer.
    """
    longo = "MT_PM_V139_Cortaderia_selloana_pumila_01_01"
    painel.name.setText(longo)
    painel.f_path.setText(f"01_MODELOS/Vegetação/Arvores/Maxtree Vol 139/{longo}.blend")
    painel.resize(300, 700)
    painel.show()
    qapp.processEvents()

    for rotulo, campo in (("nome", painel.name), ("caminho", painel.f_path)):
        exigido = campo.minimumSizeHint().width()
        assert exigido <= 120, (
            f"o {rotulo} exige {exigido}px de largura mínima e empurra o painel"
        )
    painel.close()


def test_o_texto_completo_continua_alcancavel(painel):
    """Elidir é cortar na TELA, não perder o dado — o inteiro fica no
    tooltip, e `text()` segue devolvendo tudo (é dele que a elisão parte)."""
    longo = "MT_PM_V139_Cortaderia_selloana_pumila_01_01"
    painel.name.setText(longo)

    assert painel.name.text() == longo
    assert painel.name.toolTip() == longo


def test_abrir_arquivo_que_sumiu_avisa_em_vez_de_nao_fazer_nada(qapp, tmp_path, monkeypatch):
    """Rafael: "não consigo abrir nem abrir o local deles".

    O botão chamava `openUrl` num caminho que não existe mais: o sistema
    recusa, a função devolve False, e ninguém olhava. Nada acontecia na tela
    e nada ia pro log — o tipo de falha silenciosa que as regras do projeto
    proíbem.
    """
    from PySide6.QtGui import QDesktopServices

    from assetdeck.ui.details_panel import DetailsPanel

    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda *a: pytest.fail(
                            "não devia nem tentar abrir um arquivo inexistente")))
    painel = DetailsPanel(tmp_path)
    painel._current = tmp_path / "sumiu.blend"

    avisos = []
    painel.aviso.connect(avisos.append)
    painel._open_file()

    assert len(avisos) == 1
    assert "não existe mais no disco" in avisos[0]
    assert "Relocalizar" in avisos[0], (
        "o aviso precisa dizer o que fazer a respeito, não só que deu errado")


def test_abrir_arquivo_que_existe_continua_abrindo(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    from assetdeck.ui.details_panel import DetailsPanel

    alvo = tmp_path / "existe.png"
    alvo.write_bytes(b"x")
    abertos = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: abertos.append(url) or True))
    painel = DetailsPanel(tmp_path)
    painel._current = alvo

    avisos = []
    painel.aviso.connect(avisos.append)
    painel._open_file()

    assert len(abertos) == 1
    assert avisos == []
