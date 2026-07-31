"""Scanner: classificação, fingerprint e o ciclo completo de varredura.

A "biblioteca" destes testes é uma pasta temporária com arquivos sintéticos —
mock só em teste, como manda o CLAUDE.md.
"""

import os
import time
from pathlib import Path

import pytest

from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import classify, fingerprint, scan_library


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    apply_migrations(c)
    yield c
    c.close()


@pytest.fixture
def lib(tmp_path):
    """Biblioteca sintética com um arquivo de cada família + intrusos."""
    root = tmp_path / "lib"
    (root / "texturas").mkdir(parents=True)
    (root / "texturas" / "madeira.jpg").write_bytes(b"jpg" * 100)
    (root / "texturas" / "ceu.hdr").write_bytes(b"hdr" * 100)
    (root / "modelo.blend").write_bytes(b"blend" * 100)
    (root / "luz.ies").write_bytes(b"ies" * 100)
    (root / "grade.cube").write_bytes(b"lut" * 100)
    (root / "manual.pdf").write_bytes(b"pdf" * 100)
    # Intrusos que devem ser ignorados:
    (root / "notas.xyz").write_bytes(b"desconhecido")
    (root / ".escondido.jpg").write_bytes(b"oculto")
    (root / "meta.assetdeck.json").write_bytes(b"{}")  # sidecar nosso
    return root


def _scan(conn, root):
    lib_id = libraries_repo.get_or_create(conn, root)
    return scan_library(conn, lib_id, root)


# ---- classificação e fingerprint ----

def test_classify_mapeia_tipos_certos():
    assert classify(Path("x.JPG")) == "texture"
    assert classify(Path("x.exr")) == "hdri"
    assert classify(Path("x.blend")) == "model"
    assert classify(Path("x.ies")) == "ies"
    assert classify(Path("x.cube")) == "lut"
    assert classify(Path("x.psd")) == "psd"
    assert classify(Path("x.svg")) == "vector"
    assert classify(Path("x.dwg")) == "vector"   # CAD, a pedido do Rafael
    assert classify(Path("x.mtlx")) == "other"
    assert classify(Path("x.xyz")) is None


def test_fingerprint_estavel_e_sensivel(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"conteudo-igual")
    b.write_bytes(b"conteudo-igual")
    c = tmp_path / "c.bin"
    c.write_bytes(b"conteudo-DIFERENTE")

    assert fingerprint(a) == fingerprint(b)   # mesmo conteúdo → mesmo hash
    assert fingerprint(a) != fingerprint(c)   # conteúdo diferente → hash diferente


# ---- ciclo de varredura ----

def test_primeira_varredura_indexa_tudo(conn, lib):
    stats = _scan(conn, lib)

    assert stats.added == 6
    assert stats.ignored == 1          # notas.xyz (oculto e sidecar nem entram)
    assert assets_repo.count_active(conn) == 6

    tipos = {r["asset_type"] for r in conn.execute("SELECT asset_type FROM assets")}
    assert tipos == {"texture", "hdri", "model", "ies", "lut", "reference"}
    # Todo asset tem exatamente um arquivo principal:
    orfaos = conn.execute(
        """SELECT COUNT(*) AS n FROM assets a
           WHERE (SELECT COUNT(*) FROM files f
                  WHERE f.asset_id = a.id AND f.is_primary = 1) != 1"""
    ).fetchone()["n"]
    assert orfaos == 0


def test_revarredura_e_idempotente(conn, lib):
    _scan(conn, lib)
    stats = _scan(conn, lib)

    assert stats.added == 0
    assert stats.unchanged == 6
    assert assets_repo.count_active(conn) == 6  # nada duplicou


def test_arquivo_modificado_e_atualizado_sem_trocar_uuid(conn, lib):
    _scan(conn, lib)
    uuid_antes = conn.execute(
        "SELECT uuid FROM assets WHERE name = 'madeira'"
    ).fetchone()["uuid"]

    alvo = lib / "texturas" / "madeira.jpg"
    alvo.write_bytes(b"conteudo novo bem maior" * 50)
    os.utime(alvo, ns=(time.time_ns(), time.time_ns() + 1_000_000_000))

    stats = _scan(conn, lib)

    assert stats.updated == 1
    uuid_depois = conn.execute(
        "SELECT uuid FROM assets WHERE name = 'madeira'"
    ).fetchone()["uuid"]
    assert uuid_antes == uuid_depois  # identidade estável: uuid NUNCA muda


def test_arquivo_sumido_ganha_missing_since_e_nada_e_apagado(conn, lib):
    _scan(conn, lib)
    (lib / "luz.ies").unlink()  # o teste apaga; o app JAMAIS apaga

    stats = _scan(conn, lib)

    assert stats.missing == 1
    row = conn.execute(
        "SELECT missing_since, deleted_at FROM files WHERE rel_path = 'luz.ies'"
    ).fetchone()
    assert row["missing_since"] is not None
    assert row["deleted_at"] is None            # soft nem foi preciso: linha intacta
    assert assets_repo.count_active(conn) == 6  # asset continua existindo


def test_arquivo_que_volta_tem_missing_since_limpo(conn, lib):
    _scan(conn, lib)
    conteudo = (lib / "luz.ies").read_bytes()
    (lib / "luz.ies").unlink()
    _scan(conn, lib)  # marca sumido

    (lib / "luz.ies").write_bytes(conteudo)  # "voltou"
    stats = _scan(conn, lib)

    assert stats.reappeared == 1
    row = conn.execute(
        "SELECT missing_since FROM files WHERE rel_path = 'luz.ies'"
    ).fetchone()
    assert row["missing_since"] is None


def test_parada_a_pedido_interrompe_sem_corromper(conn, lib):
    lib_id = libraries_repo.get_or_create(conn, lib)
    chamadas = {"n": 0}

    def stop_depois_de_2():
        chamadas["n"] += 1
        return chamadas["n"] > 2

    stats = scan_library(conn, lib_id, lib, should_stop=stop_depois_de_2)

    assert stats.aborted is True
    # O que entrou, entrou íntegro; a próxima varredura completa o resto:
    stats2 = scan_library(conn, lib_id, lib)
    assert stats2.aborted is False
    assert assets_repo.count_active(conn) == 6


def test_raiz_inexistente_da_erro_legivel(conn, tmp_path):
    lib_id = libraries_repo.get_or_create(conn, tmp_path / "nao-existe")
    with pytest.raises(RuntimeError, match="library_root"):
        scan_library(conn, lib_id, tmp_path / "nao-existe")


def test_get_or_create_nao_duplica_library(conn, tmp_path):
    a = libraries_repo.get_or_create(conn, tmp_path)
    b = libraries_repo.get_or_create(conn, tmp_path)
    assert a == b
