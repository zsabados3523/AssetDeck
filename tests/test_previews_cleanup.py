"""Fatia 104 — purga de previews órfãos.

`previews_repo.soft_delete` tira a linha da galeria mas nunca apagou o
arquivo copiado. Esta rotina apaga de `previews/` o que nenhuma linha
ATIVA referencia, seguindo o padrão do projeto: planejar sem tocar em
disco, confirmar, executar logando cada falha sem derrubar o lote.
"""

import pytest
from PIL import Image

from assetdeck import previews_cleanup
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "modelo.blend").write_bytes(b"blend" * 40)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    externa = tmp_path / "meu_render.png"
    Image.new("RGB", (128, 128), (200, 40, 40)).save(externa)
    pdir = tmp_path / "previews"
    yield conn, root, pdir, externa
    conn.close()


def _aid(conn, name):
    return conn.execute(
        "SELECT id FROM assets WHERE name = ?", (name,)
    ).fetchone()["id"]


def test_orfao_de_linha_soft_deletada_e_apagado_ativo_preservado(env):
    conn, _, pdir, externa = env
    aid = _aid(conn, "modelo")

    vivo = previews_repo.add(conn, aid, externa, pdir)
    orfao = previews_repo.add(conn, aid, externa, pdir)
    pid_orfao = previews_repo.list_for(conn, aid)[-1]["id"]
    previews_repo.soft_delete(conn, pid_orfao)

    plano = previews_cleanup.planejar(conn, pdir)

    assert plano.orfaos == [orfao]
    assert plano.total_orfaos == 1
    assert plano.arquivos_em_uso == 1
    assert plano.bytes_orfaos == orfao.stat().st_size
    assert vivo.exists() and orfao.exists()  # planejar não tocou em disco

    apagados, liberados, falhas = previews_cleanup.executar(plano)

    assert (apagados, falhas) == (1, 0)
    assert liberados > 0
    assert not orfao.exists()
    assert vivo.exists()  # linha ativa: intocado


def test_file_path_externo_nunca_e_candidato(env):
    """Linha ativa apontando pra fora de previews/ (imagem escolhida direto,
    nunca copiada) não pode ser apagada — e não confunde a varredura."""
    conn, _, pdir, externa = env
    aid = _aid(conn, "modelo")
    pdir.mkdir()

    conn.execute(
        "INSERT INTO previews (asset_id, file_path, kind, origin, is_cover) "
        "VALUES (?, ?, 'image', 'user', 1)",
        (aid, str(externa)),
    )
    conn.commit()
    solto = pdir / "abandonado.png"
    Image.new("RGB", (32, 32)).save(solto)

    plano = previews_cleanup.planejar(conn, pdir)

    assert plano.orfaos == [solto]
    assert externa.exists()
    previews_cleanup.executar(plano)
    assert externa.exists()  # fora da pasta do app: jamais tocado


def test_arquivo_que_nao_e_imagem_fica_onde_esta(env):
    conn, _, pdir, _ = env
    pdir.mkdir()
    (pdir / "notas.json").write_text("{}")
    (pdir / "escrita.tmp").write_bytes(b"x")

    plano = previews_cleanup.planejar(conn, pdir)

    assert plano.orfaos == []
    previews_cleanup.executar(plano)
    assert (pdir / "notas.json").exists()
    assert (pdir / "escrita.tmp").exists()


def test_falha_ao_apagar_um_nao_derruba_o_lote(env, monkeypatch):
    conn, _, pdir, externa = env
    aid = _aid(conn, "modelo")
    a = previews_repo.add(conn, aid, externa, pdir)
    b = previews_repo.add(conn, aid, externa, pdir)
    for pid in [r["id"] for r in previews_repo.list_for(conn, aid)]:
        previews_repo.soft_delete(conn, pid)

    plano = previews_cleanup.planejar(conn, pdir)
    assert set(plano.orfaos) == {a, b}

    real_unlink = type(a).unlink

    def unlink_falho(self, *args, **kwargs):
        if self.name == a.name:
            raise OSError("permissão negada (simulado)")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(a), "unlink", unlink_falho)

    apagados, liberados, falhas = previews_cleanup.executar(plano)

    assert (apagados, falhas) == (1, 1)
    assert a.exists()          # o que falhou continua lá
    assert not b.exists()      # o resto do lote foi em frente


def test_pasta_inexistente_da_plano_vazio(env, tmp_path):
    conn, _, _, _ = env
    plano = previews_cleanup.planejar(conn, tmp_path / "nem_existe")
    assert plano.total_orfaos == 0
    assert previews_cleanup.executar(plano) == (0, 0, 0)
