"""Render de capas: seleção de pendentes, comando do Blender e erros."""

import subprocess
from pathlib import Path

import pytest

from assetdeck.blender import render
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "cadeira.blend").write_bytes(b"blend" * 30)
    (root / "mesa.blend").write_bytes(b"blend" * 31)
    (root / "textura.jpg").write_bytes(b"j" * 40)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, lib_id, root, tmp_path
    conn.close()


def test_script_de_render_existe():
    assert render.script_path().is_file()
    assert render.script_path().is_absolute()  # o Flatpak resolve /app se relativo


def test_lista_so_modelos_sem_capa(env):
    conn, lib_id, root, tmp_path = env
    pendentes = render.models_without_cover(conn, lib_id, root)
    assert {n for _i, n, _p in pendentes} == {"cadeira", "mesa"}  # textura fora

    alvo = pendentes[0][0]
    capa = tmp_path / "capa.png"
    capa.write_bytes(b"png")
    previews_repo.add(conn, alvo, capa, tmp_path / "previews")

    restantes = render.models_without_cover(conn, lib_id, root)
    assert len(restantes) == 1  # o que ganhou capa saiu da fila


def test_caminhos_devolvidos_sao_absolutos(env):
    conn, lib_id, root, _ = env
    for _id, _nome, caminho in render.models_without_cover(conn, lib_id, root):
        assert Path(caminho).is_absolute()
        assert Path(caminho).is_file()


def test_arquivo_inexistente_da_erro_legivel(tmp_path):
    r = render.render_thumbnail(tmp_path / "nao-existe.blend", tmp_path / "o.png",
                                comando=["echo"])
    assert r.ok is False
    assert "não existe" in r.erro.lower()


def test_sem_blender_da_erro_legivel(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "blender_command", lambda: None)
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")
    r = render.render_thumbnail(alvo, tmp_path / "o.png")
    assert r.ok is False and "não encontrado" in r.erro.lower()


def test_render_que_nao_gera_imagem_e_falha(tmp_path):
    """Comando que roda mas não escreve nada = falha (não sucesso silencioso)."""
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")
    r = render.render_thumbnail(alvo, tmp_path / "saida.png", comando=["true"])
    assert r.ok is False


def test_motivo_extrai_a_excecao(tmp_path):
    class FakeProc:
        returncode = 1
        stdout = "Read blend: /x.blend\nFra:1 Mem:20M\n"
        stderr = ("Traceback (most recent call last):\n"
                  '  File "<string>", line 3, in <module>\n'
                  "    cena.world.use_nodes = True\n"
                  "AttributeError: 'NoneType' object has no attribute 'use_nodes'\n")

    motivo = render._motivo(FakeProc())
    assert motivo.startswith("AttributeError")  # não a linha de contexto


def test_blender_command_encontra_algo_ou_none():
    cmd = render.blender_command()
    assert cmd is None or (isinstance(cmd, list) and cmd)


@pytest.fixture
def dir_visivel_ao_flatpak():
    """Pasta que o Blender Flatpak enxerga.

    O /tmp do pytest NÃO serve: o sandbox tem /tmp próprio (descoberto no
    F2). Só o HOME é compartilhado.
    """
    import shutil
    import tempfile

    base = Path.home() / ".cache" / "assetdeck"
    base.mkdir(parents=True, exist_ok=True)
    caminho = Path(tempfile.mkdtemp(prefix="pytest_render_", dir=base))
    yield caminho
    shutil.rmtree(caminho, ignore_errors=True)


@pytest.mark.skipif(render.blender_command() is None,
                    reason="Blender não instalado nesta máquina")
def test_render_de_verdade_gera_png(dir_visivel_ao_flatpak):
    """Integração real: cria um .blend com um cubo e renderiza a capa."""
    cmd = render.blender_command()
    blend = dir_visivel_ao_flatpak / "cubo.blend"
    criar = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    subprocess.run([*cmd, "-b", "--python-expr", criar],
                   capture_output=True, timeout=300, check=False)
    assert blend.is_file(), "não consegui criar o .blend de teste"

    destino = dir_visivel_ao_flatpak / "capa.png"
    resultado = render.render_thumbnail(blend, destino, size=64)

    assert resultado.ok, resultado.erro
    assert destino.is_file() and destino.stat().st_size > 0
