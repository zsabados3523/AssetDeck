"""Navegação de pastas ponta a ponta na janela real (Fatia 32).

Arquivo próprio porque precisa de uma biblioteca COM subpastas — o
fixture `janela` de test_main_window.py é plano de propósito.
"""

import pytest
from PIL import Image

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.indexer.scanner import scan_library
from assetdeck.ui.main_window import MainWindow


@pytest.fixture
def janela(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETDECK_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ASSETDECK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ASSETDECK_CACHE_DIR", str(tmp_path / "cache"))
    config.ensure_dirs()

    root = tmp_path / "lib"
    (root / "Modelos" / "Cadeiras").mkdir(parents=True)
    (root / "Texturas").mkdir()
    (root / "Modelos" / "poste.blend").write_bytes(b"b" * 40)
    (root / "Modelos" / "Cadeiras" / "eames.blend").write_bytes(b"e" * 40)
    Image.new("RGB", (32, 32)).save(root / "Texturas" / "madeira.jpg")

    conn = connect(config.db_path())
    apply_migrations(conn)
    lib_id = libraries_repo.get_or_create(conn, root)
    scan_library(conn, lib_id, root)

    w = MainWindow(conn, str(root), config.db_path(), config.thumbs_dir())
    yield w
    w.close()
    conn.close()


def test_comeca_sem_para_onde_navegar(janela):
    assert janela.back_btn.isEnabled() is False
    assert janela.fwd_btn.isEnabled() is False
    assert janela.up_btn.isEnabled() is False  # já está na raiz


def test_entrar_numa_pasta_habilita_voltar_e_subir(janela):
    janela._go_to_dir("Modelos")

    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"
    assert janela.back_btn.isEnabled() is True
    assert janela.up_btn.isEnabled() is True
    assert janela.fwd_btn.isEnabled() is False  # nada no futuro ainda


def test_voltar_e_avancar_refazem_o_caminho(janela):
    janela._go_to_dir("Modelos")
    janela._go_to_dir("Modelos/Cadeiras")

    janela._go_back()
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"
    assert janela.fwd_btn.isEnabled() is True

    janela._go_back()
    assert janela._breadcrumb_full == "BIBLIOTECA (TUDO)"
    assert janela.back_btn.isEnabled() is False

    janela._go_forward()
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"


def test_voltar_refiltra_a_grade_de_verdade(janela):
    """O botão não pode só trocar o título e deixar a grade parada."""
    janela._go_to_dir("Texturas")
    assert janela.model.rowCount() == 1  # madeira.jpg

    janela._go_back()
    assert janela.model.rowCount() == 3  # a biblioteca inteira


def test_subir_um_nivel(janela):
    janela._go_to_dir("Modelos/Cadeiras")

    janela._go_up()
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"

    janela._go_up()
    assert janela._breadcrumb_full == "BIBLIOTECA (TUDO)"
    assert janela.up_btn.isEnabled() is False


def test_arvore_acompanha_a_navegacao(janela):
    """A seleção na árvore lateral tem de seguir os botões — ela é a fonte
    da verdade do filtro de pasta (`_current_filters_dict`)."""
    janela._go_to_dir("Modelos/Cadeiras")
    janela._go_back()

    assert janela.folders.currentItem().data(0, 32) == ""


def test_navegar_do_meio_descarta_o_futuro(janela):
    janela._go_to_dir("Modelos")
    janela._go_to_dir("Modelos/Cadeiras")
    janela._go_back()
    janela._go_to_dir("Texturas")

    assert janela.fwd_btn.isEnabled() is False
    janela._go_back()
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"


def test_reindexar_mantem_a_pasta_atual(janela):
    """Antes da Fatia 32 a varredura jogava de volta pra raiz e ainda
    deixava o breadcrumb mostrando a pasta antiga."""
    janela._go_to_dir("Modelos/Cadeiras")

    janela._reload_all()

    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS › CADEIRAS"
    assert janela.folders.currentItem().data(0, 32) == "Modelos/Cadeiras"
    assert janela.model.rowCount() == 1


def test_pasta_que_sumiu_cai_na_raiz(janela):
    """Histórico apontando pra pasta que não existe mais não pode deixar o
    breadcrumb mentindo."""
    janela._go_to_dir("Modelos")
    janela._go_to_dir("Pasta/Que/Sumiu")

    assert janela._breadcrumb_full == "BIBLIOTECA (TUDO)"
    assert janela.folders.currentItem().data(0, 32) == ""


def test_caminho_longo_corta_pela_esquerda_mantendo_a_pasta_atual(janela):
    """A linha divide espaço com 3 botões de navegação, 6 de categoria,
    nota, resolução e slider. Cortar pela direita esconderia justamente a
    pasta em que o Rafael está."""
    janela.breadcrumb.setFixedWidth(120)
    janela._go_to_dir("Modelos/Cadeiras")

    texto = janela.breadcrumb.text()
    assert texto != janela._breadcrumb_full  # encurtou mesmo
    assert texto.endswith("CADEIRAS")        # a pasta atual sobreviveu
    assert texto.startswith("…")
    assert janela.breadcrumb.toolTip() == "BIBLIOTECA › MODELOS › CADEIRAS"


def test_smart_collection_entra_no_historico(janela):
    """Decisão do Rafael: aplicar uma Smart Collection é navegação como
    qualquer outra, o Voltar tem de desfazê-la."""
    janela._go_to_dir("Modelos")
    janela._restore_filters({"dir_prefix": "Texturas"})

    assert janela._breadcrumb_full == "BIBLIOTECA › TEXTURAS"
    janela._go_back()
    assert janela._breadcrumb_full == "BIBLIOTECA › MODELOS"
