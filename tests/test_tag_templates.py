"""Templates de tags (Fatia 35): conteúdo, poda por nível e aplicação."""

import re

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import tags as tags_repo
from assetdeck.ui import tag_icons, tag_templates as tt


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    yield c
    c.close()


def _caminhos(nos, prefixo=""):
    """Todos os caminhos 'A/B/C' da árvore, para comparar níveis."""
    saida = []
    for n in nos:
        p = f"{prefixo}/{n.nome}" if prefixo else n.nome
        saida.append(p)
        saida.extend(_caminhos(n.filhos, p))
    return saida


def _todos(nos):
    for n in nos:
        yield n
        yield from _todos(n.filhos)


# ---- conteúdo ----

def test_os_tres_niveis_sao_o_mesmo_tronco():
    """Se um nível divergisse do outro, aplicar em sequência criaria tags
    duplicadas em vez de só acrescentar folhas."""
    resumido = set(_caminhos(tt.arvore("arquitetura", tt.RESUMIDO)))
    balanceado = set(_caminhos(tt.arvore("arquitetura", tt.BALANCEADO)))
    completo = set(_caminhos(tt.arvore("arquitetura", tt.COMPLETO)))

    assert resumido < balanceado < completo


def test_cada_nivel_cresce_em_profundidade():
    def prof(nos, d=1):
        return max((prof(n.filhos, d + 1) for n in nos if n.filhos), default=d)

    assert prof(tt.arvore("arquitetura", tt.RESUMIDO)) == 1
    assert prof(tt.arvore("arquitetura", tt.BALANCEADO)) == 2
    assert prof(tt.arvore("arquitetura", tt.COMPLETO)) == 3


def test_tamanhos_batem_com_o_prometido():
    """Faixas largas de propósito: o alvo é pegar crescimento acidental
    (um nível virar 300 tags), não travar o conteúdo em número exato."""
    assert tt.contar(tt.arvore("arquitetura", tt.RESUMIDO)) == 8
    assert 30 <= tt.contar(tt.arvore("arquitetura", tt.BALANCEADO)) <= 50
    assert 80 <= tt.contar(tt.arvore("arquitetura", tt.COMPLETO)) <= 130


def test_todo_icone_citado_existe_de_verdade():
    """Nome errado viraria tag sem ícone silenciosamente."""
    for no in _todos(tt.ARQUITETURA):
        if no.icone is not None:
            assert no.icone in tag_icons.CHAVES, f"{no.nome}: ícone {no.icone!r}"


def test_toda_cor_e_hex_valido():
    for no in _todos(tt.ARQUITETURA):
        if no.cor is not None:
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", no.cor), f"{no.nome}: {no.cor!r}"


def test_nao_ha_irmaos_com_o_mesmo_nome():
    """UNIQUE(parent_id, name) no schema — irmãos repetidos quebrariam."""
    def conferir(nos, caminho="raiz"):
        nomes = [n.nome for n in nos]
        assert len(nomes) == len(set(nomes)), f"nomes repetidos em {caminho}"
        for n in nos:
            conferir(n.filhos, n.nome)

    conferir(tt.ARQUITETURA)


def test_nivel_desconhecido_explode_alto():
    with pytest.raises(ValueError, match="desconhecido"):
        tt.arvore("arquitetura", "inventado")


def test_template_desconhecido_explode_alto():
    with pytest.raises(ValueError, match="desconhecido"):
        tt.arvore("inventado", tt.BALANCEADO)


# ---- múltiplos templates (Fatia 55) ----

def test_registro_tem_arquitetura_e_os_templates_novos():
    esperados = {
        "arquitetura", "propaganda", "construcao", "filme_animacao",
        "gamedev", "design_produto", "vfx_simulacao",
    }
    assert esperados <= tt.TEMPLATES.keys()


def test_arquitetura_continua_a_mesma_arvore_de_antes():
    """Regressão: generalizar pra vários templates não pode alterar o
    conteúdo do template que já existia."""
    assert tt.TEMPLATES["arquitetura"].raizes is tt.ARQUITETURA


@pytest.mark.parametrize("chave", [
    "propaganda", "construcao", "filme_animacao", "gamedev",
    "design_produto", "vfx_simulacao",
])
def test_todo_template_novo_tem_conteudo_valido(chave):
    """Mesmas garantias estruturais da Arquitetura, pros templates novos:
    3 níveis crescem em profundidade, ícones existem, cores são hex
    válido, sem irmãos com nome repetido (UNIQUE do schema quebraria)."""
    raizes = tt.TEMPLATES[chave].raizes

    resumido = set(_caminhos(tt.arvore(chave, tt.RESUMIDO)))
    balanceado = set(_caminhos(tt.arvore(chave, tt.BALANCEADO)))
    completo = set(_caminhos(tt.arvore(chave, tt.COMPLETO)))
    assert resumido <= balanceado <= completo  # "<=", não "<": nível 2 pode
    # não ter 3º nível pra podar ainda (Balanceado == Completo é válido)

    for no in _todos(raizes):
        if no.icone is not None:
            assert no.icone in tag_icons.CHAVES, f"{chave}/{no.nome}: ícone {no.icone!r}"
        if no.cor is not None:
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", no.cor), f"{chave}/{no.nome}: {no.cor!r}"

    def conferir(nos, caminho="raiz"):
        nomes = [n.nome for n in nos]
        assert len(nomes) == len(set(nomes)), f"{chave}: nomes repetidos em {caminho}"
        for n in nos:
            conferir(n.filhos, n.nome)

    conferir(raizes)


def test_templates_diferentes_nao_se_misturam(conn):
    """Aplicar 'construcao' não pode criar nada de 'propaganda' — são
    árvores independentes, cada uma na sua chave."""
    tt.aplicar(conn, "construcao", tt.RESUMIDO)

    nomes = {t["name"] for t in tags_repo.list_tree(conn)}
    raizes_propaganda = {n.nome for n in tt.PROPAGANDA}
    assert not (nomes & raizes_propaganda)


# ---- aplicação ----

def test_aplicar_num_banco_vazio_cria_a_hierarquia(conn):
    r = tt.aplicar(conn, "arquitetura", tt.BALANCEADO)

    assert r.existentes == 0
    assert r.criadas == tt.contar(tt.arvore("arquitetura", tt.BALANCEADO))

    linhas = {t["name"]: t for t in tags_repo.list_tree(conn)}
    assert "Materiais" in linhas and linhas["Materiais"]["parent_id"] is None
    madeira = linhas["Madeira"]
    assert madeira["parent_id"] == linhas["Materiais"]["id"]
    assert madeira["icon"] == "tag-madeira"


def test_filho_sem_cor_herda_a_do_pai(conn):
    tt.aplicar(conn, "arquitetura", tt.BALANCEADO)
    linhas = {t["name"]: t for t in tags_repo.list_tree(conn)}

    assert linhas["Arbustos"]["color"] == linhas["Vegetação"]["color"]
    # e quem tem cor própria não herda
    assert linhas["Madeira"]["color"] != linhas["Materiais"]["color"]


def test_aplicar_duas_vezes_nao_duplica(conn):
    primeira = tt.aplicar(conn, "arquitetura", tt.BALANCEADO)
    antes = len(tags_repo.list_tree(conn))

    segunda = tt.aplicar(conn, "arquitetura", tt.BALANCEADO)

    assert len(tags_repo.list_tree(conn)) == antes
    assert segunda.criadas == 0
    assert segunda.existentes == primeira.criadas


def test_subir_de_nivel_so_acrescenta_folhas(conn):
    tt.aplicar(conn, "arquitetura", tt.RESUMIDO)
    r = tt.aplicar(conn, "arquitetura", tt.BALANCEADO)

    assert r.existentes == tt.contar(tt.arvore("arquitetura", tt.RESUMIDO))
    assert len(tags_repo.list_tree(conn)) == tt.contar(tt.arvore("arquitetura", tt.BALANCEADO))


def test_aplicar_nao_estraga_tag_que_ja_existia(conn):
    """A garantia que o Rafael pediu: a tag dele sai ilesa — cor, ícone e
    os assets marcados."""
    materiais = tags_repo.create(conn, "Materiais", color="#FF0000", icon="tag-estrela")
    metal = tags_repo.create(conn, "Metal", parent_id=materiais,
                             color="#00FF00", icon="tag-flor")
    conn.execute("INSERT INTO libraries (id, name, root_path) "
                 "VALUES (1, 'l', '/tmp/x')")  # antes do asset: há FK
    conn.execute("INSERT INTO assets (uuid, library_id, name, asset_type) "
                 "VALUES ('u1', 1, 'peca', 'model')")
    asset_id = conn.execute("SELECT id FROM assets").fetchone()["id"]
    tags_repo.assign(conn, asset_id, metal)

    tt.aplicar(conn, "arquitetura", tt.COMPLETO)

    linhas = {t["id"]: t for t in tags_repo.list_tree(conn)}
    assert linhas[materiais]["color"] == "#FF0000"
    assert linhas[materiais]["icon"] == "tag-estrela"
    assert linhas[metal]["color"] == "#00FF00"
    assert linhas[metal]["icon"] == "tag-flor"
    assert [t["id"] for t in tags_repo.tags_of(conn, asset_id)] == [metal]


def test_aplicar_nao_mexe_em_tag_de_fora(conn):
    minha = tags_repo.create(conn, "Projeto Casa X", color="#123456")

    tt.aplicar(conn, "arquitetura", tt.BALANCEADO)

    linha = next(t for t in tags_repo.list_tree(conn) if t["id"] == minha)
    assert linha["name"] == "Projeto Casa X"
    assert linha["color"] == "#123456"


# ---- prévia ----

def test_previa_marca_o_que_ja_existe(conn):
    tags_repo.create(conn, "Materiais")

    itens = tt.previa(conn, "arquitetura", tt.RESUMIDO)
    por_nome = {no.nome: existe for no, _, _, existe in itens}

    assert por_nome["Materiais"] is True
    assert por_nome["Vegetação"] is False


def test_previa_nao_cria_nada(conn):
    tt.previa(conn, "arquitetura", tt.COMPLETO)
    assert tags_repo.list_tree(conn) == []


def test_previa_traz_profundidade_e_cor_efetiva(conn):
    itens = tt.previa(conn, "arquitetura", tt.BALANCEADO)
    por_nome = {no.nome: (prof, cor) for no, prof, cor, _ in itens}

    assert por_nome["Materiais"][0] == 0
    assert por_nome["Madeira"][0] == 1
    assert por_nome["Arbustos"][1] == por_nome["Vegetação"][1]  # herdou
