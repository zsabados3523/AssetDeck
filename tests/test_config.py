"""Config: isolamento por env vars e resiliência a config.json corrompido."""

import json

from assetdeck import config


def test_env_vars_isolam_os_diretorios(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))

    assert config.config_dir() == tmp_path / "cfg"
    assert config.db_path() == tmp_path / "data" / "assetdeck.db"
    assert config.thumbs_dir() == tmp_path / "cache" / "thumbs"
    assert config.models3d_cache_dir() == tmp_path / "cache" / "models3d"


def test_primeira_execucao_cria_config_com_padroes(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    cfg = config.load_config()
    assert cfg["library_root"] == config.DEFAULTS["library_root"]
    salvo = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert salvo == config.DEFAULTS
    assert cfg["theme_mode"] == "claro"


def test_config_corrompido_e_preservado_e_recriado(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text("{isso nao é json", encoding="utf-8")

    cfg = config.load_config()

    assert cfg == config.DEFAULTS  # voltou aos padrões…
    quebrados = list(tmp_path.glob("config.json.broken-*"))
    assert len(quebrados) == 1  # …e o arquivo ruim foi preservado, não apagado


def test_chaves_novas_sao_completadas_em_config_antigo(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"library_root": "/outro/lugar"}), encoding="utf-8"
    )
    cfg = config.load_config()
    assert cfg["library_root"] == "/outro/lugar"  # valor do usuário vence
    assert cfg["backup_keep"] == config.DEFAULTS["backup_keep"]  # default completa


def test_cena_de_render_tem_defaults(tmp_path, monkeypatch):
    """Fatia 38: um config.json de antes desta fatia não tinha essas 3
    chaves — o mecanismo genérico de completar defaults já cobre, mas
    nomeando aqui documenta o contrato e pega erro de digitação."""
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(json.dumps({}), encoding="utf-8")

    cfg = config.load_config()

    assert cfg["render_bg_color"] == config.DEFAULTS["render_bg_color"]
    assert cfg["render_bg_strength"] == config.DEFAULTS["render_bg_strength"]
    assert cfg["render_sun_energy"] == config.DEFAULTS["render_sun_energy"]
