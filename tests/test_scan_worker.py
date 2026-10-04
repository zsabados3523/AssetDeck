"""Pós-processamento da varredura (ScanWorker.run): o toggle de preview
automático por nome (Fatia 57) tem que ser respeitado — ligado aplica,
desligado (o padrão) não mexe em nada."""

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import previews as previews_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.scan_worker import ScanWorker


def _preparar_banco():
    """ScanWorker.run() só conecta — quem aplica as migrations é o
    bootstrap do app (`assetdeck.app.run`), não o worker."""
    conn = connect(config.db_path())
    apply_migrations(conn)
    conn.close()


def _biblioteca_com_par_de_mesmo_nome(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "Cadeira.blend").write_bytes(b"b" * 30)
    (root / "Cadeira.jpg").write_bytes(b"j" * 30)
    return root


def _asset_id_do_blend(conn):
    return conn.execute(
        "SELECT a.id FROM assets a JOIN files f ON f.asset_id = a.id "
        "WHERE f.rel_path = 'Cadeira.blend'"
    ).fetchone()["id"]


def test_toggle_desligado_por_padrao_nao_aplica(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    _preparar_banco()
    root = _biblioteca_com_par_de_mesmo_nome(tmp_path)

    ScanWorker(config.db_path(), root).run()

    conn = connect(config.db_path())
    assert previews_repo.list_for(conn, _asset_id_do_blend(conn)) == []
    conn.close()


def test_toggle_ligado_aplica_o_casamento_por_nome(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    _preparar_banco()
    cfg = config.load_config()
    cfg["auto_match_previews_by_name"] = True
    config.save_config(cfg)
    root = _biblioteca_com_par_de_mesmo_nome(tmp_path)

    ScanWorker(config.db_path(), root).run()

    conn = connect(config.db_path())
    galeria = previews_repo.list_for(conn, _asset_id_do_blend(conn))
    assert len(galeria) == 1
    assert galeria[0]["origin"] == "auto"
    conn.close()


def test_toggle_de_ocultar_origem_tambem_e_respeitado(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    _preparar_banco()
    cfg = config.load_config()
    cfg["auto_match_previews_by_name"] = True
    cfg["auto_match_hide_source"] = True
    config.save_config(cfg)
    root = _biblioteca_com_par_de_mesmo_nome(tmp_path)

    ScanWorker(config.db_path(), root).run()

    conn = connect(config.db_path())
    imagem_id = conn.execute(
        "SELECT a.id FROM assets a JOIN files f ON f.asset_id = a.id "
        "WHERE f.rel_path = 'Cadeira.jpg'"
    ).fetchone()["id"]
    hidden = conn.execute("SELECT hidden FROM assets WHERE id = ?", (imagem_id,)).fetchone()
    assert hidden["hidden"] == 1
    conn.close()


def test_progress_conta_so_a_biblioteca_sendo_escaneada(tmp_path, monkeypatch, qapp):
    """Fatia 70: achado com screenshot real — o "N assets" do progresso
    (e do rodapé depois) somava TODAS as bibliotecas do banco, não só a
    que estava sendo indexada agora."""
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    _preparar_banco()

    outra_root = tmp_path / "outra_lib"
    outra_root.mkdir()
    for i in range(5):
        (outra_root / f"asset_{i}.blend").write_bytes(b"b" * 10)
    conn = connect(config.db_path())
    outra_id = libraries_repo.get_or_create(conn, outra_root)
    scan_library(conn, outra_id, outra_root)
    conn.close()

    root = _biblioteca_com_par_de_mesmo_nome(tmp_path)  # 2 assets só

    progresso_recebido = []
    worker = ScanWorker(config.db_path(), root)
    worker.progress.connect(
        lambda _done, fase, ativos: progresso_recebido.append((fase, ativos)))
    worker.run()

    assert progresso_recebido, "nenhum sinal de progresso emitido"
    assert all(
        ativos == (0 if fase == -3 else 2)
        for fase, ativos in progresso_recebido
    ), (
        "a contagem deve incluir somente a biblioteca atual e refletir se o lote "
        f"já foi inserido; veio {progresso_recebido}"
    )


def test_worker_aplica_quantidade_de_processos_salva_no_config(
    tmp_path, monkeypatch, qapp,
):
    from assetdeck.indexer import scanner

    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    _preparar_banco()
    cfg = config.load_config()
    cfg["scan_workers"] = 8
    config.save_config(cfg)
    root = _biblioteca_com_par_de_mesmo_nome(tmp_path)

    recebidos = []
    monkeypatch.setattr(
        scanner, "_abrir_pool", lambda workers: recebidos.append(workers))
    ScanWorker(config.db_path(), root).run()

    assert recebidos == [8]
