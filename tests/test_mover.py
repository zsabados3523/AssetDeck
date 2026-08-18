"""Mover assets de pasta dentro da biblioteca (Fatia 85).

Este módulo ESCREVE na biblioteca — uma das duas exceções à regra de
somente-leitura (a outra é o batch rename). Por isso os testes cobrem
tanto o caminho feliz quanto cada recusa: o que protege a biblioteca do
Rafael é justamente o que o planejador se RECUSA a fazer.
"""

import pytest
from PIL import Image

from assetdeck import mover
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def lib(tmp_path):
    """Uma biblioteca com os três casos reais dele:

    - Cosmos: asset DONO da própria pasta, com previews/ e textura embaixo
    - Maxtree: vários modelos dividindo a mesma pasta
    - uma pasta de destino vazia
    """
    root = tmp_path / "lib"

    cosmos = root / "VASOS" / "Chair_125_029"
    (cosmos / "previews").mkdir(parents=True)
    (cosmos / "Chair_125_029.blend").write_bytes(b"b" * 40)
    Image.new("RGB", (16, 16)).save(cosmos / "previews" / "Chair_125_029_01.png")
    Image.new("RGB", (16, 16)).save(cosmos / "textura.png")

    maxtree = root / "VASOS" / "Maxtree_Vol_139"
    maxtree.mkdir(parents=True)
    for i in (1, 2):
        (maxtree / f"MT_Planta_0{i}.blend").write_bytes(b"b" * 40)

    (root / "ARVORES").mkdir(parents=True)
    Image.new("RGB", (16, 16)).save(root / "ARVORES" / "placeholder.png")

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root
    conn.close()


def _id(conn, rel_path):
    return conn.execute(
        "SELECT a.id FROM assets a JOIN files f ON f.asset_id = a.id "
        "WHERE f.rel_path = ? AND f.is_primary = 1", (rel_path,),
    ).fetchone()["id"]


# ------------------------------------------------------ planejar --

def test_planeja_mover_asset_dono_da_propria_pasta(lib):
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")

    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    assert len(plano.mover) == 1
    m = plano.mover[0]
    assert m.origem == "VASOS/Chair_125_029"
    assert m.destino == "ARVORES/Chair_125_029"
    assert m.arquivos >= 3      # .blend + preview + textura
    assert plano.recusar == []


def test_recusa_asset_que_divide_pasta(lib):
    """Um Maxtree divide a pasta com dezenas de irmãos — mover levaria
    todos junto. O Rafael aceitou esse limite explicitamente."""
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Maxtree_Vol_139/MT_Planta_01.blend")

    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    assert plano.mover == []
    assert len(plano.recusar) == 1
    assert "divide a pasta" in plano.recusar[0].motivo


def test_recusa_quando_ja_existe_pasta_de_mesmo_nome_no_destino(lib):
    """NUNCA sobrescrever: colisão é erro, não substituição."""
    conn, lib_id, root = lib
    (root / "ARVORES" / "Chair_125_029").mkdir(parents=True)
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")

    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    assert plano.mover == []
    assert "já existe" in plano.recusar[0].motivo


def test_recusa_mover_para_a_pasta_onde_ja_esta(lib):
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")

    plano = mover.planejar(conn, lib_id, root, [alvo], "VASOS")

    assert plano.mover == []
    assert "já está" in plano.recusar[0].motivo


def test_planejar_nao_toca_em_disco(lib):
    """O plano é só uma conta — nada sai do lugar até `executar`."""
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")

    mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    assert (root / "VASOS" / "Chair_125_029" / "Chair_125_029.blend").is_file()
    assert not (root / "ARVORES" / "Chair_125_029").exists()


# ------------------------------------------------------ executar --

def test_executar_move_a_pasta_inteira_e_reaponta_o_banco(lib):
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")
    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    movidos, falhas = mover.executar(conn, lib_id, root, plano)

    assert (movidos, falhas) == (1, 0)
    # disco: a pasta inteira foi, com preview e textura
    assert not (root / "VASOS" / "Chair_125_029").exists()
    assert (root / "ARVORES" / "Chair_125_029" / "Chair_125_029.blend").is_file()
    assert (root / "ARVORES" / "Chair_125_029" / "previews"
            / "Chair_125_029_01.png").is_file()
    assert (root / "ARVORES" / "Chair_125_029" / "textura.png").is_file()
    # banco: TODOS os arquivos da pasta reapontados, não só o principal
    caminhos = [r["rel_path"] for r in conn.execute(
        "SELECT rel_path FROM files WHERE deleted_at IS NULL")]
    assert not [c for c in caminhos if c.startswith("VASOS/Chair_125_029")]
    assert len([c for c in caminhos if c.startswith("ARVORES/Chair_125_029/")]) >= 3


def test_o_asset_continua_achavel_pelo_id_depois_de_mover(lib):
    """Mover é mudar de lugar, não recriar: tags, notas e favoritos vivem
    no asset_id, então ele tem de sobreviver."""
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")
    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    mover.executar(conn, lib_id, root, plano)

    novo = _id(conn, "ARVORES/Chair_125_029/Chair_125_029.blend")
    assert novo == alvo


def test_falha_em_um_nao_derruba_o_lote(lib, monkeypatch):
    """Mesmo padrão do batch_rename: item problemático é pulado e logado."""
    conn, lib_id, root = lib
    alvo = _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend")
    plano = mover.planejar(conn, lib_id, root, [alvo], "ARVORES")

    def explode(*_a, **_k):
        raise OSError("disco cheio (simulado)")

    monkeypatch.setattr(mover.shutil, "move", explode)
    movidos, falhas = mover.executar(conn, lib_id, root, plano)

    assert (movidos, falhas) == (0, 1)
    # e o banco NÃO foi mexido: o arquivo segue onde estava
    assert _id(conn, "VASOS/Chair_125_029/Chair_125_029.blend") == alvo
