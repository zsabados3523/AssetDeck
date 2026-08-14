"""Biblioteca que sai do lugar: achar de novo e repontar (Fatia 53).

Bug de origem: o SSD do Rafael montou em `/mnt/<uuid>` em vez do
`/media/rafael/SSD` gravado no config. O app abria normal (miniaturas vêm do
cache) e só quebrava ao LER um arquivo original — arrastar imagem para virar
preview de um modelo falhava com FileNotFoundError apenas no log.
"""

import pytest

from assetdeck import library_root
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    apply_migrations(c)
    yield c
    c.close()


# ---- resolve() ----


def test_caminho_existente_resolve_para_ele_mesmo(tmp_path):
    raiz = tmp_path / "lib"
    raiz.mkdir()

    res = library_root.resolve(raiz)

    assert res.ok
    assert res.found == raiz
    assert not res.moved and not res.missing


def test_acha_a_biblioteca_no_novo_ponto_de_montagem(tmp_path, monkeypatch):
    """O caso do Rafael: mesmo final de caminho, ponto de montagem diferente."""
    novo_mount = tmp_path / "mnt" / "284A670E4A66D7D8"
    real = novo_mount / "Documentos" / "{cura}" / "BIBLIOTECA {CURA}"
    real.mkdir(parents=True)
    monkeypatch.setattr(library_root, "_mount_roots", lambda: [novo_mount])

    gravado = tmp_path / "media" / "rafael" / "SSD" / \
        "Documentos" / "{cura}" / "BIBLIOTECA {CURA}"
    res = library_root.resolve(gravado)

    assert res.moved
    assert res.found == real
    assert res.configured == gravado


def test_prefere_o_sufixo_mais_longo(tmp_path, monkeypatch):
    """Dois candidatos batem; vence o que casa MAIS pedaços do caminho —
    o curto é coincidência de nome de pasta."""
    mount = tmp_path / "mnt"
    curto = mount / "BIBLIOTECA"
    longo = mount / "Documentos" / "cura" / "BIBLIOTECA"
    curto.mkdir(parents=True)
    longo.mkdir(parents=True)
    monkeypatch.setattr(library_root, "_mount_roots", lambda: [mount])

    gravado = tmp_path / "media" / "SSD" / "Documentos" / "cura" / "BIBLIOTECA"
    res = library_root.resolve(gravado)

    assert res.found == longo


def test_disco_desconectado_nao_acha_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(library_root, "_mount_roots", lambda: [tmp_path / "vazio"])

    res = library_root.resolve(tmp_path / "media" / "SSD" / "BIBLIOTECA")

    assert res.missing
    assert res.found is None
    assert not res.ok and not res.moved


def test_ponto_de_montagem_ilegivel_nao_derruba_a_busca(tmp_path, monkeypatch):
    """Disco removido no meio do caminho levanta OSError no iterdir —
    isso é informação, não motivo para o app não abrir."""
    quebrado = tmp_path / "quebrado"
    quebrado.mkdir()
    quebrado.chmod(0o000)
    try:
        assert library_root._subdirs(quebrado) == []
    finally:
        quebrado.chmod(0o755)  # senão o tmp_path não é limpo


# ---- repoint() ----


def test_repoint_troca_a_raiz_sem_criar_biblioteca_nova(conn, tmp_path):
    """Só o config não bastaria: get_or_create criaria uma library NOVA e
    vazia, e a grade do Rafael (72 mil assets) sumiria da tela."""
    antiga = tmp_path / "media" / "SSD" / "BIBLIOTECA"
    nova = tmp_path / "mnt" / "uuid" / "BIBLIOTECA"
    lib_id = libraries_repo.get_or_create(conn, antiga)

    assert library_root.repoint(conn, antiga, nova) == 1

    assert libraries_repo.get_or_create(conn, nova) == lib_id
    total = conn.execute("SELECT COUNT(*) c FROM libraries").fetchone()["c"]
    assert total == 1


def test_repoint_sem_linha_correspondente_nao_mexe_em_nada(conn, tmp_path):
    libraries_repo.get_or_create(conn, tmp_path / "outra")

    assert library_root.repoint(conn, tmp_path / "inexistente", tmp_path / "nova") == 0

    raizes = [r["root_path"] for r in conn.execute("SELECT root_path FROM libraries")]
    assert raizes == [str(tmp_path / "outra")]


# ---- _confirmar_biblioteca() na abertura do app ----


def test_abertura_com_biblioteca_no_lugar_nao_abre_dialogo(conn, tmp_path, qapp):
    """Caminho feliz: nada de diálogo modal atrapalhando a abertura."""
    from assetdeck.app import _confirmar_biblioteca

    raiz = tmp_path / "lib"
    raiz.mkdir()
    cfg = {"library_root": str(raiz)}

    assert _confirmar_biblioteca(conn, cfg, silencioso=False) == str(raiz)
    assert cfg["library_root"] == str(raiz)


def test_modo_screenshot_nao_trava_num_dialogo(conn, tmp_path, qapp):
    """`--screenshot` roda sem ninguém na frente da tela; um QMessageBox
    modal travaria a captura para sempre."""
    from assetdeck.app import _confirmar_biblioteca

    sumida = tmp_path / "disco-desconectado" / "lib"
    cfg = {"library_root": str(sumida)}

    assert _confirmar_biblioteca(conn, cfg, silencioso=True) == str(sumida)
