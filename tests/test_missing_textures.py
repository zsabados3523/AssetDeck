"""Checagem de texturas quebradas dentro de um .blend (Fatia 40) — só
leitura, nunca escreve no arquivo do usuário. Molde: tests/test_render.py."""

import subprocess
from pathlib import Path

import pytest

from assetdeck.blender import missing_textures as mt
from assetdeck.blender.render import blender_command


def test_sem_blender_da_erro_legivel(tmp_path, monkeypatch):
    monkeypatch.setattr(mt, "blender_command", lambda: None)
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")

    r = mt.list_missing_textures(alvo)

    assert r.ok is False and "não encontrado" in r.erro.lower()


def test_arquivo_inexistente_da_erro_legivel(tmp_path):
    r = mt.list_missing_textures(tmp_path / "nao-existe.blend", comando=["echo"])
    assert r.ok is False
    assert "não existe" in r.erro.lower()


def test_le_a_linha_marcadora_do_stdout(tmp_path):
    """Fake que imprime a mesma linha que o script real imprimiria —
    prova o parsing sem precisar do Blender."""
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")
    linha = ('ASSETDECK_TEXTURAS_JSON {"perdidas": '
            '[{"nome": "foo", "caminho_esperado": "/x/foo.png"}], '
            '"recuperadas_auto": 2}')
    comando = ["python3", "-c", f"print({linha!r})"]

    r = mt.list_missing_textures(alvo, comando=comando)

    assert r.ok is True
    assert r.perdidas == [{"nome": "foo", "caminho_esperado": "/x/foo.png"}]
    assert r.recuperadas_auto == 2


def test_stdout_sem_a_linha_marcadora_da_erro(tmp_path):
    """Blender travou antes de imprimir (crash, exceção) — não pode virar
    'nada quebrado' por engano."""
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")

    r = mt.list_missing_textures(alvo, comando=["echo", "ruído qualquer, sem marcador"])

    assert r.ok is False
    assert r.perdidas == []


def test_timeout_da_erro_legivel(tmp_path, monkeypatch):
    def _estoura(*a, **k):
        raise subprocess.TimeoutExpired(cmd="blender", timeout=1)

    monkeypatch.setattr(mt.subprocess, "run", _estoura)
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")

    r = mt.list_missing_textures(alvo, comando=["blender"])

    assert r.ok is False
    assert "s" in r.erro  # menciona o tempo, não crasha


# ---- integração real com Blender ----

@pytest.fixture
def dir_visivel_ao_flatpak():
    """Mesma necessidade de test_render.py: o /tmp do pytest não é visível
    ao sandbox do Flatpak, só o HOME."""
    import shutil
    import tempfile

    base = Path.home() / ".cache" / "assetdeck"
    base.mkdir(parents=True, exist_ok=True)
    caminho = Path(tempfile.mkdtemp(prefix="pytest_missingtex_", dir=base))
    yield caminho
    shutil.rmtree(caminho, ignore_errors=True)


@pytest.mark.skipif(blender_command() is None,
                    reason="Blender não instalado nesta máquina")
def test_detecta_textura_quebrada_de_verdade(dir_visivel_ao_flatpak):
    """Cria um .blend com uma imagem cujo caminho não existe e confirma
    que a checagem real acha ela.

    `use_fake_user = True` é necessário: sem isso o datablock de imagem
    sem nenhum uso real (não ligado a material/objeto) é descartado no
    save_as_mainfile — descoberto rodando de verdade, não presumido.
    """
    cmd = blender_command()
    blend = dir_visivel_ao_flatpak / "quebrado.blend"
    criar = (
        "import bpy;"
        "img = bpy.data.images.new('textura_quebrada', 1, 1);"
        "img.filepath = '//nao_existe_de_verdade.png';"
        "img.source = 'FILE';"
        "img.use_fake_user = True;"
        f"bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    )
    subprocess.run([*cmd, "-b", "--python-expr", criar],
                   capture_output=True, timeout=120, check=False)
    assert blend.is_file(), "não consegui criar o .blend de teste"

    resultado = mt.list_missing_textures(blend)

    assert resultado.ok, resultado.erro
    assert len(resultado.perdidas) == 1
    assert resultado.perdidas[0]["nome"] == "textura_quebrada"
    assert resultado.perdidas[0]["caminho_esperado"].endswith("nao_existe_de_verdade.png")


@pytest.mark.skipif(blender_command() is None,
                    reason="Blender não instalado nesta máquina")
def test_blend_sem_textura_quebrada_devolve_lista_vazia(dir_visivel_ao_flatpak):
    cmd = blender_command()
    blend = dir_visivel_ao_flatpak / "limpo.blend"
    criar = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    subprocess.run([*cmd, "-b", "--python-expr", criar],
                   capture_output=True, timeout=120, check=False)
    assert blend.is_file()

    resultado = mt.list_missing_textures(blend)

    assert resultado.ok, resultado.erro
    assert resultado.perdidas == []
