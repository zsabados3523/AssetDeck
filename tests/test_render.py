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


# ---- cena configurável (Fatia 38) ----

def test_hex_para_linear_pontos_conhecidos():
    assert render.hex_to_linear_rgb("#000000") == (0.0, 0.0, 0.0)
    r, g, b = render.hex_to_linear_rgb("#FFFFFF")
    assert (round(r, 6), round(g, 6), round(b, 6)) == (1.0, 1.0, 1.0)
    # 0x80/255 ≈ 0.502 sRGB -> ~0.216 linear (ponto de referência conhecido)
    r, _, _ = render.hex_to_linear_rgb("#808080")
    assert 0.21 < r < 0.22


def test_hex_para_linear_e_mais_escuro_que_o_srgb():
    """A curva sRGB->linear sempre escurece o valor pra tons médios — se
    a conversão estivesse invertida ou ausente, a cor sairia mais clara
    do que o Rafael escolheu no seletor."""
    r, _, _ = render.hex_to_linear_rgb("#959599")  # o default de hoje
    assert r < 0x95 / 255


def _capturar_cmd(monkeypatch, tmp_path):
    """Troca subprocess.run por um fake que grava o cmd e escreve o PNG
    esperado, pra inspecionar os argumentos sem depender do Blender."""
    capturado = {}

    def _fake_run(cmd, **kw):
        capturado["cmd"] = cmd
        (tmp_path / "saida.png").write_bytes(b"png")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render.subprocess, "run", _fake_run)
    return capturado


def test_render_thumbnail_sem_cena_usa_os_defaults_de_sempre(tmp_path, monkeypatch):
    """Ninguém que já chama render_thumbnail() (nem os testes daqui) pode
    quebrar por causa dos parâmetros novos."""
    capturado = _capturar_cmd(monkeypatch, tmp_path)
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")

    render.render_thumbnail(alvo, tmp_path / "saida.png", comando=["blender"])

    cauda = capturado["cmd"][-5:]
    assert cauda == [str(c) for c in (*render.BG_COLOR_PADRAO, render.BG_STRENGTH_PADRAO,
                                      render.SUN_ENERGY_PADRAO)]


def test_render_thumbnail_passa_a_cena_customizada(tmp_path, monkeypatch):
    capturado = _capturar_cmd(monkeypatch, tmp_path)
    alvo = tmp_path / "x.blend"
    alvo.write_bytes(b"b")

    render.render_thumbnail(alvo, tmp_path / "saida.png", comando=["blender"],
                            bg_color=(1.0, 0.0, 0.0), bg_strength=5.0, sun_energy=9.0)

    cauda = capturado["cmd"][-5:]
    assert cauda == ["1.0", "0.0", "0.0", "5.0", "9.0"]


def test_script_de_render_existe():
    assert render.script_path().is_file()
    assert render.script_path().is_absolute()  # o Flatpak resolve /app se relativo


def test_script_pede_cycles_e_fundo_transparente():
    """Guarda rápida, sem precisar do Blender (os testes de integração real,
    mais abaixo, já provam o COMPORTAMENTO — este é só pra pegar rápido uma
    regressão óbvia de quem edite o texto do script sem querer).

    Fatia 102: Rafael pediu explicitamente Cycles em vez de EEVEE, e fundo
    transparente em vez de fundo colorido sólido.
    """
    texto = render.script_path().read_text(encoding="utf-8")
    assert 'cena.render.engine = "CYCLES"' in texto
    assert "cena.render.film_transparent = True" in texto
    assert '"BLENDER_EEVEE"' not in texto
    assert "film_transparent = False" not in texto


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


# ---- gerar capa só de alguns assets (Fatia 101) ----

def test_asset_ids_restringe_ao_subconjunto(env):
    """Rafael: "gerar o preview porém somente de alguns assets", pelo botão
    direito. `models_without_cover` precisa aceitar um recorte, não só
    "todos os modelos sem capa"."""
    conn, lib_id, root, _ = env
    cadeira_id = next(i for i, n, _p in render.models_without_cover(conn, lib_id, root)
                      if n == "cadeira")

    so_cadeira = render.models_without_cover(conn, lib_id, root, asset_ids=[cadeira_id])

    assert {n for _i, n, _p in so_cadeira} == {"cadeira"}


def test_asset_ids_vazio_nao_bate_no_banco(env):
    """Lista vazia é resultado vazio, sem consultar — evita um `IN ()` que
    o SQLite aceita mas que custaria uma varredura à toa."""
    conn, lib_id, root, _ = env
    assert render.models_without_cover(conn, lib_id, root, asset_ids=[]) == []


def test_asset_ids_ignora_quem_ja_tem_capa(env):
    """O recorte não pula a checagem de capa — só some o universo. Selecionar
    um asset que JÁ tem capa não deve mandar renderizar de novo."""
    conn, lib_id, root, tmp_path = env
    pendentes = render.models_without_cover(conn, lib_id, root)
    alvo = pendentes[0][0]
    previews_repo.add(conn, alvo, _png_valido(tmp_path), tmp_path / "previews")

    assert render.models_without_cover(conn, lib_id, root, asset_ids=[alvo]) == []


def test_models_for_render_inclui_e_identifica_capa_existente(env):
    conn, lib_id, root, tmp_path = env
    alvo = render.models_without_cover(conn, lib_id, root)[0][0]
    previews_repo.add(conn, alvo, _png_valido(tmp_path), tmp_path / "previews")

    jobs = render.models_for_render(
        conn, lib_id, root, asset_ids=[alvo], overwrite_existing=True,
    )

    assert len(jobs) == 1
    assert jobs[0][0] == alvo
    assert jobs[0][3] is True


def _png_valido(tmp_path):
    from PIL import Image

    caminho = tmp_path / "capa.png"
    Image.new("RGB", (4, 4)).save(caminho)
    return caminho


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
    """Integração real: cria um .blend com um cubo e renderiza a capa.

    `--factory-startup` ao CRIAR o cubo também (achado escrevendo a Fatia
    102): sem ela, o Blender fica pendurado ao encerrar em modo headless
    nesta máquina — os add-ons do Rafael atrapalham o `atexit`. Sem
    `--factory-startup` medi 40s de travamento até o timeout matar o
    processo; com ela, sai limpo. `render_thumbnail()` (o que é testado de
    verdade) já usava a flag desde sempre — só faltava aqui, no comando que
    PREPARA o teste.
    """
    cmd = render.blender_command()
    blend = dir_visivel_ao_flatpak / "cubo.blend"
    criar = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    subprocess.run([*cmd, "-b", "--factory-startup", "--python-expr", criar],
                   capture_output=True, timeout=300, check=False)
    assert blend.is_file(), "não consegui criar o .blend de teste"

    destino = dir_visivel_ao_flatpak / "capa.png"
    resultado = render.render_thumbnail(blend, destino, size=64)

    assert resultado.ok, resultado.erro
    assert destino.is_file() and destino.stat().st_size > 0


@pytest.mark.skipif(render.blender_command() is None,
                    reason="Blender não instalado nesta máquina")
def test_fundo_sai_transparente_de_verdade(dir_visivel_ao_flatpak):
    """Prova ponta a ponta (Fatia 102, Rafael: "teria como deixar o fundo
    transparente?"): o canto da imagem — garantidamente fora do objeto,
    nunca alcançado por ele (MARGEM=1.05 é apertado, mas um círculo
    inscrito num quadrado nunca chega no canto) — tem de ter alfa ZERO."""
    from PIL import Image

    cmd = render.blender_command()
    blend = dir_visivel_ao_flatpak / "cubo.blend"
    criar = f"import bpy; bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    subprocess.run([*cmd, "-b", "--factory-startup", "--python-expr", criar],
                   capture_output=True, timeout=300, check=False)
    assert blend.is_file(), "não consegui criar o .blend de teste"

    destino = dir_visivel_ao_flatpak / "capa.png"
    resultado = render.render_thumbnail(blend, destino, size=64)
    assert resultado.ok, resultado.erro

    img = Image.open(destino)
    assert img.mode == "RGBA", f"PNG sem canal alfa (modo {img.mode})"
    r, g, b, a = img.getpixel((0, 0))
    assert a == 0, f"canto devia ser transparente, alfa={a}"


@pytest.mark.skipif(render.blender_command() is None,
                    reason="Blender não instalado nesta máquina")
def test_sun_energy_muda_o_brilho_do_objeto_de_verdade(dir_visivel_ao_flatpak):
    """Prova ponta a ponta que `sun_energy` (a intensidade da luz KEY do
    3-point lighting desde a Fatia 102) realmente chega no shader — não só
    que o argumento foi passado no comando.

    Antes desta fatia `sun_energy` iluminava o fundo visível e este teste
    lia o pixel do CANTO; com o fundo transparente isso não serve mais
    (alfa=0 ali sempre, não importa a luz). Agora mede o CENTRO — onde o
    cubo está — e confirma que uma key mais forte deixa o objeto mais
    claro. Comparação DIFERENCIAL, não contra um valor absoluto: o Blender
    aplica view transform (AgX) por cima da cor linear, então prever o
    pixel exato exigiria reimplementar essa curva aqui.
    """
    from PIL import Image

    cmd = render.blender_command()
    blend = dir_visivel_ao_flatpak / "cubo_sem_luz.blend"
    # Remove a luz padrão da cena de abertura do Blender ANTES de salvar —
    # sem isso o .blend "já tem luz própria" e o script (corretamente)
    # respeita ela em vez de montar o 3-point lighting, e `sun_energy` (que
    # só afeta a KEY do 3-point) nunca chegaria a valer nada aqui.
    criar = (
        "import bpy; "
        "[bpy.data.objects.remove(o, do_unlink=True) for o in list(bpy.data.objects) "
        "if o.type == 'LIGHT']; "
        f"bpy.ops.wm.save_as_mainfile(filepath=r'{blend}')"
    )
    subprocess.run([*cmd, "-b", "--factory-startup", "--python-expr", criar],
                   capture_output=True, timeout=300, check=False)
    assert blend.is_file(), "não consegui criar o .blend de teste"

    def _brilho_do_objeto(sun_energy: float) -> int:
        destino = dir_visivel_ao_flatpak / f"capa_{sun_energy}.png"
        resultado = render.render_thumbnail(
            blend, destino, size=64, sun_energy=sun_energy)
        assert resultado.ok, resultado.erro
        img = Image.open(destino).convert("RGB")
        centro = img.size[0] // 2, img.size[1] // 2
        return sum(img.getpixel(centro))  # soma dos 3 canais = brilho

    escuro = _brilho_do_objeto(0.3)
    claro = _brilho_do_objeto(8.0)

    assert claro > escuro, (
        f"key mais forte não deixou o objeto mais claro (escuro={escuro}, "
        f"claro={claro})"
    )
