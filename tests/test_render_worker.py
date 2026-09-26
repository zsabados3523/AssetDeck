"""RenderWorker: fila de renders (Fatia 38 — a cena vem do config, lida
FRESCA a cada rodada, sem precisar reconstruir o worker nem reabrir o app)."""

import pytest

from assetdeck import config
from assetdeck.blender.render import RenderResult, hex_to_linear_rgb
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui import render_worker as rw


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    root = tmp_path / "lib"
    root.mkdir()
    (root / "cadeira.blend").write_bytes(b"blend" * 30)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    conn.close()
    return tmp_path, root


def _worker(tmp_path, root, capturados, monkeypatch):
    def _fake_render(blend_path, dest, size, bg_color=None, bg_strength=None,
                     sun_energy=None):
        capturados.append((bg_color, bg_strength, sun_energy))
        return RenderResult(False, erro="não renderiza de verdade no teste")

    monkeypatch.setattr(rw, "render_thumbnail", _fake_render)
    return rw.RenderWorker(tmp_path / "t.db", root, tmp_path / "previews")


def test_run_le_a_cena_do_config(qapp, env, monkeypatch):
    tmp_path, root = env
    cfg = config.load_config()
    cfg["render_bg_color"] = "#ff0000"
    cfg["render_bg_strength"] = 9.0
    cfg["render_sun_energy"] = 4.0
    config.save_config(cfg)

    capturados = []
    _worker(tmp_path, root, capturados, monkeypatch).run()

    assert len(capturados) == 1
    bg_color, bg_strength, sun_energy = capturados[0]
    assert bg_color == hex_to_linear_rgb("#ff0000")
    assert bg_strength == 9.0
    assert sun_energy == 4.0


def test_run_le_o_config_de_novo_a_cada_chamada(qapp, env, monkeypatch):
    """A garantia central desta fatia: mudar a preferência entre duas
    rodadas não precisa reabrir o app nem recriar o worker."""
    tmp_path, root = env
    config.load_config()  # cria com padrões

    capturados = []
    worker = _worker(tmp_path, root, capturados, monkeypatch)
    worker.run()  # primeira rodada, cena padrão
    primeira = capturados[-1]

    cfg = config.load_config()
    cfg["render_sun_energy"] = 15.0
    config.save_config(cfg)

    # segunda rodada só é possível porque o mock devolve falha (não marca
    # capa) — o asset continua "sem capa" pra models_without_cover achar
    worker2 = _worker(tmp_path, root, capturados, monkeypatch)
    worker2.run()
    segunda = capturados[-1]

    assert primeira[2] == 3.0        # default de sempre
    assert segunda[2] == 15.0        # já pegou o valor novo, sem reconstruir nada


# ---- restringir a fila a um subconjunto (Fatia 101) ----

def test_worker_repassa_asset_ids_pra_models_without_cover(qapp, env, monkeypatch):
    """A fila (`RenderWorker`) precisa levar o recorte até a consulta que
    decide o que renderizar — sem isso "gerar preview de alguns" acaba
    renderizando a biblioteca inteira de novo."""
    tmp_path, root = env
    capturado = {}

    def _fake_mwc(conn, lib_id, library_root, asset_ids=None):
        capturado["asset_ids"] = asset_ids
        return []  # fila vazia: o teste termina rápido, sem chamar o Blender

    monkeypatch.setattr(rw, "models_without_cover", _fake_mwc)

    worker = rw.RenderWorker(tmp_path / "t.db", root, tmp_path / "previews",
                             asset_ids=[7, 8])
    worker.run()

    assert capturado["asset_ids"] == [7, 8]


def test_worker_usa_fila_com_capas_existentes_quando_sobrescrever(qapp, env, monkeypatch):
    tmp_path, root = env
    capturado = {}

    def _fake_models_for_render(conn, lib_id, library_root, asset_ids=None,
                               overwrite_existing=False):
        capturado["asset_ids"] = asset_ids
        capturado["overwrite_existing"] = overwrite_existing
        return []

    monkeypatch.setattr(rw, "models_for_render", _fake_models_for_render)

    worker = rw.RenderWorker(
        tmp_path / "t.db", root, tmp_path / "previews", asset_ids=[7],
        overwrite_existing=True,
    )
    worker.run()

    assert capturado == {"asset_ids": [7], "overwrite_existing": True}


def test_worker_sem_asset_ids_continua_pegando_tudo(qapp, env, monkeypatch):
    """`None` é o comportamento de sempre — o botão geral de Configurações
    não pode virar um recorte por engano."""
    tmp_path, root = env
    capturado = {}

    def _fake_mwc(conn, lib_id, library_root, asset_ids=None):
        capturado["asset_ids"] = asset_ids
        return []

    monkeypatch.setattr(rw, "models_without_cover", _fake_mwc)

    rw.RenderWorker(tmp_path / "t.db", root, tmp_path / "previews").run()

    assert capturado["asset_ids"] is None


def test_controller_start_repassa_asset_ids_ao_worker(qapp, env, monkeypatch):
    tmp_path, root = env
    capturado = {}
    orig_init = rw.RenderWorker.__init__

    def _espiao(self, *a, **kw):
        capturado["asset_ids"] = kw.get("asset_ids")
        capturado["overwrite_existing"] = kw.get("overwrite_existing")
        orig_init(self, *a, **kw)

    monkeypatch.setattr(rw.RenderWorker, "__init__", _espiao)
    monkeypatch.setattr(rw, "models_without_cover", lambda *a, **kw: [])

    controller = rw.RenderController(tmp_path / "t.db", root, tmp_path / "previews")
    controller.start(lambda *a: None, lambda *a: None, lambda *a: None,
                     asset_ids=[3], overwrite_existing=True)
    controller.shutdown()

    assert capturado == {"asset_ids": [3], "overwrite_existing": True}
