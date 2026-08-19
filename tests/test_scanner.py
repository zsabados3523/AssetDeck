"""Scanner: classificação, fingerprint e o ciclo completo de varredura.

A "biblioteca" destes testes é uma pasta temporária com arquivos sintéticos —
mock só em teste, como manda o CLAUDE.md.
"""

import os
import time
from pathlib import Path

import cv2
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


def test_classify_outros_programas_vira_model():
    """Fatia 37: Revit/SketchUp/USD/Alembic — só reconhecer e catalogar,
    sem preview real (sem SDK do fabricante). Entram como 'model' de
    propósito: categoria, dependências e chip de extensão já funcionam
    automático, sem precisar de valor novo no enum."""
    assert classify(Path("Projeto.RVT")) == "model"     # Revit
    assert classify(Path("fachada.skp")) == "model"      # SketchUp
    for ext in ("usd", "usda", "usdc", "usdz"):
        assert classify(Path(f"cena.{ext}")) == "model", ext
    assert classify(Path("anim.abc")) == "model"          # Alembic


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


# ------------------------------------- varredura paralela (Fatia 86) --

def _linhas_do_banco(conn):
    return [tuple(r) for r in conn.execute(
        """SELECT rel_path, size_bytes, content_hash, width, height,
                  has_alpha, bit_depth, phash, dominant_color
           FROM files ORDER BY rel_path""")]


def test_paralelo_produz_exatamente_o_mesmo_banco_que_serial(tmp_path):
    """O ganho de velocidade não pode custar UM bit de diferença.

    Importa especialmente pelo phash: a detecção de duplicados compara por
    IGUALDADE EXATA, sem tolerância. Se o cálculo variasse entre serial e
    paralelo, arquivos indexados em passadas diferentes deixariam de casar
    entre si — e ninguém perceberia até procurar duplicados.
    """
    from PIL import Image

    raiz = tmp_path / "lib"
    (raiz / "sub").mkdir(parents=True)
    for i in range(12):
        Image.new("RGB", (40 + i, 30 + i), (i * 9, 60, 200 - i * 5)).save(
            raiz / "sub" / f"tex_{i:02d}.png")
    (raiz / "modelo.blend").write_bytes(b"blend" * 50)

    bancos = []
    for workers in (1, 2):
        conn = connect(tmp_path / f"t{workers}.db")
        apply_migrations(conn)
        lib_id = libraries_repo.get_or_create(conn, raiz)
        stats = scan_library(conn, lib_id, raiz, workers=workers)
        assert stats.added == 13
        bancos.append(_linhas_do_banco(conn))
        conn.close()

    assert bancos[0] == bancos[1]


def test_arquivo_intocado_nao_vai_pro_pool(tmp_path):
    """A paralelização é pra arquivo NOVO ou MUDADO. Numa reindexação a
    maioria está intocada, e mandar todos pro pool desperdiçaria justamente
    onde não há trabalho a fazer."""
    from PIL import Image

    from assetdeck.indexer.scanner import _precisa_calcular

    raiz = tmp_path / "lib"
    raiz.mkdir()
    img = raiz / "tex.png"
    Image.new("RGB", (32, 32)).save(img)

    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, raiz)
    scan_library(conn, lib_id, raiz, workers=1)

    known = {row["rel_path"]: row for row in conn.execute(
        """SELECT f.id, f.rel_path, f.size_bytes, f.mtime_ns, f.missing_since,
                  f.width, f.phash, f.dominant_color
           FROM files f JOIN assets a ON a.id = f.asset_id
           WHERE a.library_id = ?""", (lib_id,))}

    assert _precisa_calcular(raiz, img, known) is False

    img.write_bytes(img.read_bytes() + b"\x00")   # mudou de tamanho
    assert _precisa_calcular(raiz, img, known) is True
    conn.close()


# ---- os processos da varredura não podem afogar a máquina ----

def test_worker_da_varredura_usa_uma_thread_e_prioridade_baixa():
    """Rafael, 2026-08-19: "meu PC fica com 100% de uso de CPU e está
    começando a dar erros".

    O OpenCV abre uma thread POR NÚCLEO em cada processo (16 na máquina
    dele). Com 4 processos de varredura são até 64 threads disputando 16
    núcleos — o trabalho não anda mais rápido (o paralelismo útil já está
    no nível de processo, medido em 4), só deixa o computador inutilizável
    enquanto indexa.

    O teste passa por um pool DE VERDADE e pergunta ao processo filho, em
    vez de conferir que o código foi escrito de um certo jeito: é o filho
    que precisa estar com uma thread só e baixa prioridade.
    """
    from assetdeck.indexer import scanner

    pool = scanner._abrir_pool(2)
    if pool is None:
        pytest.skip("pool de processos indisponível nesta máquina")
    try:
        prioridade = pool.submit(os.getpriority, os.PRIO_PROCESS, 0).result(timeout=120)
        threads = pool.submit(cv2.getNumThreads).result(timeout=120)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    assert threads == 1, f"worker abriu {threads} threads de OpenCV, devia ser 1"
    assert prioridade >= 10, (
        f"worker rodando com prioridade {prioridade} — devia ceder passagem "
        "pro que o Rafael estiver fazendo"
    )
