"""Ponte com o Blender: protocolo, handlers, servidor real e instalador."""

import json
import socket

import pytest

from assetdeck.bridge import handlers, installer
from assetdeck.bridge import protocol as proto
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library

TOKEN = "token-de-teste"


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "lib"
    (root / "mats").mkdir(parents=True)
    (root / "mats" / "Tijolo_2K_Color.jpg").write_bytes(b"c" * 60)
    (root / "mats" / "Tijolo_2K_Normal.jpg").write_bytes(b"n" * 60)
    (root / "ceu.hdr").write_bytes(b"h" * 60)
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)
    yield conn, root
    conn.close()


# ---- protocolo ----

def test_encode_decode_ida_e_volta():
    linha = proto.encode({"cmd": "ping", "acentuação": "ção"})
    assert linha.endswith(b"\n")
    assert proto.decode(linha.strip()) == {"cmd": "ping", "acentuação": "ção"}


def test_decode_rejeita_nao_objeto():
    with pytest.raises(ValueError):
        proto.decode("[1, 2, 3]")


# ---- handlers ----

def test_ping(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "ping"})
    assert r["ok"] and r["app"] == "assetdeck"
    assert r["library_root"] == str(root)


def test_comando_desconhecido_nao_derruba(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "formatar_hd"})
    assert r["ok"] is False and r["code"] == "unknown_command"


def test_list_assets_traz_caminho_absoluto(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "list_assets"})
    assert r["ok"]
    assert r["total"] == 3
    caminhos = [a["primary_path"] for a in r["assets"]]
    assert all(p.startswith(str(root)) for p in caminhos)  # o Blender precisa do absoluto


def test_list_assets_respeita_busca_e_tipo(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "list_assets", "search": "tijolo"})
    assert {a["name"] for a in r["assets"]} == {"Tijolo_2K_Color", "Tijolo_2K_Normal"}

    r = handlers.handle(conn, root, {"cmd": "list_assets", "types": ["hdri"]})
    assert [a["name"] for a in r["assets"]] == ["ceu"]


def test_list_assets_com_types_invalido_da_erro_legivel(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "list_assets", "types": "hdri"})
    assert r["ok"] is False and r["code"] == "bad_request"


def test_limite_de_itens_e_respeitado(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "list_assets", "limit": 1})
    assert r["returned"] == 1 and r["total"] == 3


def test_get_asset_devolve_arquivos_e_papeis(env):
    conn, root = env
    from assetdeck.indexer.grouper import apply_grouping

    apply_grouping(conn, 1)  # agrupa o set PBR
    set_id = conn.execute(
        "SELECT id FROM assets WHERE asset_type = 'pbr_set' AND deleted_at IS NULL"
    ).fetchone()["id"]

    r = handlers.handle(conn, root, {"cmd": "get_asset", "id": set_id})

    assert r["ok"]
    papeis = {f["map_role"] for f in r["files"]}
    assert papeis == {"basecolor", "normal"}
    assert sum(1 for f in r["files"] if f["is_primary"]) == 1


def test_thumb_path_vai_para_o_addon_quando_existe(env, tmp_path):
    """O add-on precisa do caminho da miniatura para mostrar preview."""
    from assetdeck.thumbs.cache import thumb_path

    conn, root = env
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    hash_ceu = conn.execute(
        "SELECT content_hash FROM files WHERE rel_path = 'ceu.hdr'"
    ).fetchone()["content_hash"]
    esperado = thumb_path(thumbs, hash_ceu)
    esperado.write_bytes(b"png falso")

    r = handlers.handle(conn, root, {"cmd": "list_assets", "types": ["hdri"]}, thumbs)

    assert r["assets"][0]["thumb_path"] == str(esperado)


def test_thumb_path_e_none_quando_nao_ha_miniatura(env, tmp_path):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "list_assets"}, tmp_path / "vazio")
    assert all(a["thumb_path"] is None for a in r["assets"])


def test_capa_customizada_vence_a_miniatura(env, tmp_path):
    from assetdeck.db.repos import previews as previews_repo

    conn, root = env
    capa = tmp_path / "minha_capa.png"
    capa.write_bytes(b"png")
    alvo = conn.execute("SELECT id FROM assets WHERE name = 'ceu'").fetchone()["id"]
    previews_repo.add(conn, alvo, capa, tmp_path / "previews")

    r = handlers.handle(conn, root, {"cmd": "list_assets", "types": ["hdri"]},
                        tmp_path / "thumbs")

    devolvido = r["assets"][0]["thumb_path"]
    assert devolvido is not None and "previews" in devolvido


def test_get_asset_inexistente(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "get_asset", "id": 99999})
    assert r["ok"] is False and r["code"] == "not_found"


def test_get_asset_sem_id(env):
    conn, root = env
    r = handlers.handle(conn, root, {"cmd": "get_asset"})
    assert r["ok"] is False and r["code"] == "bad_request"


# ---- servidor de verdade (socket real em 127.0.0.1) ----

def _fala_com_servidor(port: int, payload: bytes | dict, qapp=None) -> dict:
    """Conversa com o servidor de um thread, bombeando o event loop do Qt.

    O QTcpServer só atende enquanto o loop do Qt processa eventos — por isso
    o cliente roda em thread e o teste processa eventos até a resposta vir.
    """
    import threading
    import time

    bruto = payload if isinstance(payload, bytes) else (
        json.dumps(payload) + "\n").encode()
    resultado: dict = {}

    def cliente() -> None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                s.sendall(bruto)
                buf = bytearray()
                while b"\n" not in buf:
                    bloco = s.recv(65536)
                    if not bloco:
                        break
                    buf.extend(bloco)
            resultado["resposta"] = json.loads(
                bytes(buf).split(b"\n", 1)[0].decode()
            )
        except Exception as exc:  # o teste falha com a mensagem certa
            resultado["erro"] = exc

    t = threading.Thread(target=cliente, daemon=True)
    t.start()
    limite = time.time() + 5
    while t.is_alive() and time.time() < limite:
        if qapp is not None:
            qapp.processEvents()
        time.sleep(0.005)
    t.join(timeout=1)

    if "erro" in resultado:
        raise resultado["erro"]
    assert "resposta" in resultado, "servidor não respondeu a tempo"
    return resultado["resposta"]


@pytest.fixture
def servidor(env, qapp):
    from assetdeck.bridge.server import BridgeServer

    conn, root = env
    srv = BridgeServer(conn, root, TOKEN)
    assert srv.start(0), "servidor não subiu"  # porta 0 = o SO escolhe uma livre
    yield srv, srv.port
    srv.stop()


def test_servidor_responde_ping_de_verdade(servidor, qapp):
    _srv, port = servidor
    r = _fala_com_servidor(port, {"cmd": "ping", "token": TOKEN}, qapp)
    assert r["ok"] and r["app"] == "assetdeck"


def test_servidor_recusa_token_errado(servidor, qapp):
    _srv, port = servidor
    r = _fala_com_servidor(port, {"cmd": "ping", "token": "chute"}, qapp)
    assert r["ok"] is False and r["code"] == "bad_token"


def test_servidor_recusa_json_invalido(servidor, qapp):
    _srv, port = servidor
    r = _fala_com_servidor(port, b"isto nao e json\n", qapp)
    assert r["ok"] is False and r["code"] == "bad_json"


def test_servidor_lista_assets_por_socket(servidor, qapp):
    _srv, port = servidor
    r = _fala_com_servidor(port, {"cmd": "list_assets", "token": TOKEN}, qapp)
    assert r["ok"] and r["total"] == 3


# ---- instalador ----

def test_source_dir_existe_e_tem_o_addon():
    origem = installer.source_dir()
    assert (origem / "__init__.py").is_file()
    assert (origem / "client.py").is_file()


def test_install_copia_e_grava_config(tmp_path, monkeypatch):
    falso_blender = tmp_path / ".var/app/org.blender.Blender/config/blender"
    (falso_blender / "5.2").mkdir(parents=True)
    (falso_blender / "4.2").mkdir(parents=True)
    monkeypatch.setattr(installer, "FLATPAK_CONFIG", falso_blender)
    monkeypatch.setattr(installer, "STANDARD_CONFIG", tmp_path / "sem-config-padrao")

    destinos = installer.install("tok-123", port=45017)

    assert len(destinos) == 2  # instalou nas duas versões
    for d in destinos:
        assert (d / "__init__.py").is_file()
        cfg = json.loads((d / "bridge_config.json").read_text())
        assert cfg == {"host": "127.0.0.1", "port": 45017, "token": "tok-123"}
    # .../<versão>/scripts/addons/assetdeck_bridge
    assert destinos[0].parts[-4] == "5.2"  # mais nova primeiro


def test_install_sem_blender_da_erro_legivel(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "FLATPAK_CONFIG", tmp_path / "nao-existe-flatpak")
    monkeypatch.setattr(installer, "STANDARD_CONFIG", tmp_path / "nao-existe-padrao")
    with pytest.raises(RuntimeError, match="Não encontrei nenhuma instalação"):
        installer.install("tok")


def test_install_detecta_config_padrao_blender_portatil(tmp_path, monkeypatch):
    """Blender portátil (ex.: /home/rafael/Apps/blender-5.2.0-linux-x64) grava
    a config de usuário em ~/.config/blender, não na pasta do executável."""
    falso_padrao = tmp_path / ".config/blender"
    (falso_padrao / "5.2").mkdir(parents=True)
    monkeypatch.setattr(installer, "FLATPAK_CONFIG", tmp_path / "nao-existe-flatpak")
    monkeypatch.setattr(installer, "STANDARD_CONFIG", falso_padrao)

    destinos = installer.install("tok-portatil")

    assert len(destinos) == 1
    assert (destinos[0] / "__init__.py").is_file()


def test_reinstalar_substitui_versao_antiga(tmp_path, monkeypatch):
    falso_blender = tmp_path / ".var/app/org.blender.Blender/config/blender"
    (falso_blender / "5.2").mkdir(parents=True)
    monkeypatch.setattr(installer, "FLATPAK_CONFIG", falso_blender)
    monkeypatch.setattr(installer, "STANDARD_CONFIG", tmp_path / "sem-config-padrao")

    destino = installer.install("tok-antigo")[0]
    (destino / "lixo_da_versao_antiga.py").write_text("x")

    destino = installer.install("tok-novo")[0]

    assert not (destino / "lixo_da_versao_antiga.py").exists()
    assert json.loads((destino / "bridge_config.json").read_text())["token"] == "tok-novo"
