"""Backup rotativo: 1 por dia, poda os antigos, não toca no que não é dele."""

import sqlite3
from datetime import date

from assetdeck.backup.rotate import daily_backup


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()


def test_cria_backup_do_dia(tmp_path):
    db = tmp_path / "assetdeck.db"
    _make_db(db)
    backups = tmp_path / "backups"

    created = daily_backup(db, backups, keep=14)

    assert created is not None
    assert created.name == f"assetdeck-{date.today().isoformat()}.db"
    # O backup é um SQLite válido com os dados dentro:
    conn = sqlite3.connect(created)
    assert conn.execute("SELECT x FROM t").fetchone()[0] == 42
    conn.close()


def test_segunda_chamada_no_mesmo_dia_nao_duplica(tmp_path):
    db = tmp_path / "assetdeck.db"
    _make_db(db)
    backups = tmp_path / "backups"

    assert daily_backup(db, backups, keep=14) is not None
    assert daily_backup(db, backups, keep=14) is None
    assert len(list(backups.glob("*.db"))) == 1


def test_poda_mantem_apenas_os_mais_novos(tmp_path):
    db = tmp_path / "assetdeck.db"
    _make_db(db)
    backups = tmp_path / "backups"
    backups.mkdir()
    # Simula 5 backups antigos (nomes = datas passadas)
    for dia in ("2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"):
        (backups / f"assetdeck-{dia}.db").write_bytes(b"antigo")

    daily_backup(db, backups, keep=3)  # cria o de hoje → 6 no total, mantém 3

    restantes = sorted(p.name for p in backups.glob("assetdeck-*.db"))
    assert len(restantes) == 3
    assert restantes[-1] == f"assetdeck-{date.today().isoformat()}.db"
    assert "assetdeck-2026-07-01.db" not in restantes  # o mais antigo caiu


def test_poda_nao_toca_em_arquivos_fora_do_padrao(tmp_path):
    db = tmp_path / "assetdeck.db"
    _make_db(db)
    backups = tmp_path / "backups"
    backups.mkdir()
    intruso = backups / "minhas-notas.db"
    intruso.write_bytes(b"nao sou backup")

    daily_backup(db, backups, keep=1)

    assert intruso.exists()  # rotação jamais apaga o que não criou
