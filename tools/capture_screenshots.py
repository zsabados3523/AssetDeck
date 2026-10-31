#!/usr/bin/env python3
"""Gera capturas de tela determinísticas e atualizadas do AssetDeck.

Usa ambientes e diretórios isolados em /tmp/claude-1000/shots/ para nunca
tocar nos arquivos ou configurações do usuário.

Capturas geradas em docs/screenshots/:
  - biblioteca-claro.png: Janela principal com a biblioteca demo (modo claro)
  - biblioteca-escuro.png: Janela principal com a biblioteca demo (modo escuro)
  - visualizador-hdri.png: Visualizador 3D com panorama HDRI equirretangular
  - visualizador-modelo-3d.png: Visualizador 3D com malha OBJ (toro sombreado)
  - configuracoes.png: Janela central de configurações (modo claro)
  - configuracoes-escuro.png: Janela central de configurações (modo escuro)
  - colecoes-tags.png: Barra lateral focada em pastas, tags e coleções
  - renomear-lote.png: Diálogo de busca e substituição em lote com prévia
  - estado-vazio.png: Janela na primeira execução sem biblioteca configurada
  - duplicatas.png: Diálogo de detecção e revisão de duplicatas por conteúdo
  - busca-operadores.png: Busca booleana com operadores na barra de topo

Uso:
  python tools/capture_screenshots.py
  (ou via xvfb-run / QT_QPA_PLATFORM=offscreen)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Configuração de diretórios isolados antes de qualquer import do app
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SHOTS_DIR = Path("/tmp/claude-1000/shots")
LIB_DIR = SHOTS_DIR / "AssetDeck Demo"
CONFIG_DIR = SHOTS_DIR / "config"
DATA_DIR = SHOTS_DIR / "data"
CACHE_DIR = SHOTS_DIR / "cache"

os.environ["ASSETDECK_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["ASSETDECK_DATA_DIR"] = str(DATA_DIR)
os.environ["ASSETDECK_CACHE_DIR"] = str(CACHE_DIR)

from PIL import Image
import numpy as np

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication

from assetdeck import config
from assetdeck.db.connection import connect
from assetdeck.db.migrate import apply_migrations
from assetdeck.db.repos import assets as assets_repo
from assetdeck.db.repos import collections as collections_repo
from assetdeck.db.repos import libraries as libraries_repo
from assetdeck.db.repos import properties as properties_repo
from assetdeck.db.repos import smart_collections as smart_collections_repo
from assetdeck.db.repos import tags as tags_repo
from assetdeck.indexer.dependencies import attach_stem_match_previews, detect
from assetdeck.indexer.grouper import apply_grouping
from assetdeck.indexer.scanner import scan_library
from assetdeck.thumbs.cache import thumb_path
from assetdeck.thumbs.preview import can_preview, make_any_thumbnail
from assetdeck.ui import theme
from assetdeck.ui.batch_rename_dialog import BatchRenameDialog
from assetdeck.ui.duplicates_dialog import DuplicatesDialog
from assetdeck.ui.hdri_viewer import ensure_gl_format
from assetdeck.ui.main_window import MainWindow
from assetdeck.ui.settings_window import SettingsWindow
from assetdeck.ui.viewer_window import VisualizadorWindow

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def setup_demo_data() -> None:
    """Gera a biblioteca demo e popula o banco isolado a partir de um estado limpo."""
    if SHOTS_DIR.exists():
        print(f"Limpando diretório isolado {SHOTS_DIR} para garantir estado limpo...")
        shutil.rmtree(SHOTS_DIR, ignore_errors=True)

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Gerando biblioteca demo sintética em {LIB_DIR}...")
    from tools.make_demo_library import generate_library
    generate_library(LIB_DIR)

    config.ensure_dirs()
    cfg = config.load_config()
    cfg["library_root"] = str(LIB_DIR)
    cfg["theme_mode"] = "claro"
    cfg["scan_on_startup"] = False
    config.save_config(cfg)

    conn = connect(config.db_path())
    apply_migrations(conn)

    lib_id = libraries_repo.get_or_create(conn, LIB_DIR)
    scan_library(conn, lib_id, LIB_DIR)
    apply_grouping(conn, lib_id)
    detect(conn, lib_id)
    attach_stem_match_previews(conn, lib_id, LIB_DIR, config.previews_dir(), hide_source=True)

    # 1. Tags hierárquicas com cores e ícones
    tag_arq = tags_repo.create(conn, "Arquitetura", color="#2B6CB0")
    tag_conc = tags_repo.create(conn, "Concreto", parent_id=tag_arq, color="#718096")
    tag_mad = tags_repo.create(conn, "Madeira", parent_id=tag_arq, color="#975A16")
    tag_met = tags_repo.create(conn, "Metal", parent_id=tag_arq, color="#4A5568")

    tag_ilum = tags_repo.create(conn, "Iluminação", color="#D69E2E")
    tag_est = tags_repo.create(conn, "Estúdio", parent_id=tag_ilum, color="#DD6B20")
    tag_ext = tags_repo.create(conn, "Exterior", parent_id=tag_ilum, color="#319795")

    tag_des = tags_repo.create(conn, "Design", color="#E53E3E")
    tag_mob = tags_repo.create(conn, "Mobiliário", parent_id=tag_des, color="#805AD5")
    tag_dec = tags_repo.create(conn, "Decoração", parent_id=tag_des, color="#3182CE")

    # Aliases
    tags_repo.add_alias(conn, tag_mad, "Wood", "en")
    tags_repo.add_alias(conn, tag_conc, "Concrete", "en")
    tags_repo.add_alias(conn, tag_est, "Studio", "en")

    # Atribuição aos assets
    assets = assets_repo.list_for_grid(conn, library_id=lib_id, include_dependencies=True)
    vaso_id = None
    concreto_id = None
    ceu_id = None
    cadeira_id = None
    madeira_id = None
    metal_id = None
    torus_id = None

    for a in assets:
        rel = a["rel_path"].lower()
        aid = a["id"]
        if "piso_madeira_tabuas" in rel or "madeira_tabuas" in rel:
            madeira_id = aid
            tags_repo.assign(conn, aid, tag_mad)
            tags_repo.assign(conn, aid, tag_arq)
            assets_repo.set_rating(conn, aid, 5)
            assets_repo.set_starred(conn, aid, True)
            assets_repo.set_notes(conn, aid, "Set PBR completo com mapas de cor base, normal OpenGL, rugosidade e altura a 1024px. Ideal para pisos internos e revestimentos de madeira.")
        elif "vaso_decorativo" in rel and a["asset_type"] == "model":
            vaso_id = aid
            tags_repo.assign(conn, aid, tag_dec)
            tags_repo.assign(conn, aid, tag_des)
            assets_repo.set_rating(conn, aid, 5)
            assets_repo.set_starred(conn, aid, True)
            assets_repo.set_notes(conn, aid, "Modelo de vaso decorativo torneado em cerâmica esmaltada. Geometria limpa e normais suaves.")
        elif "concreto_industrial" in rel:
            concreto_id = aid
            tags_repo.assign(conn, aid, tag_conc)
            tags_repo.assign(conn, aid, tag_arq)
            assets_repo.set_rating(conn, aid, 5)
            assets_repo.set_starred(conn, aid, True)
            assets_repo.set_notes(conn, aid, "Set PBR completo com 4 mapas a 1024px. Textura de concreto aparente com marcas sutis de fôrma.")
        elif "ceu_ensolarado" in rel:
            ceu_id = aid
            tags_repo.assign(conn, aid, tag_ext)
            tags_repo.assign(conn, aid, tag_ilum)
            assets_repo.set_rating(conn, aid, 5)
            assets_repo.set_starred(conn, aid, True)
            assets_repo.set_notes(conn, aid, "Panorama equirretangular de céu límpido com sol a 55 graus. Excelente alcance dinâmico para iluminação natural.")
        elif "torus" in rel and a["asset_type"] == "model":
            torus_id = aid
            tags_repo.assign(conn, aid, tag_des)
            assets_repo.set_rating(conn, aid, 4)
            assets_repo.set_starred(conn, aid, True)
            assets_repo.set_notes(conn, aid, "Geometria de toro com normais suaves e acabamento terracota metálico.")
        elif "cadeira_estilizada" in rel and a["asset_type"] == "model":
            cadeira_id = aid
            tags_repo.assign(conn, aid, tag_mob)
            tags_repo.assign(conn, aid, tag_des)
            assets_repo.set_rating(conn, aid, 4)
            assets_repo.set_starred(conn, aid, True)
        elif "aco" in rel or "metal" in rel:
            metal_id = aid
            tags_repo.assign(conn, aid, tag_met)
            tags_repo.assign(conn, aid, tag_arq)
            assets_repo.set_rating(conn, aid, 4)
        elif "estudio" in rel:
            tags_repo.assign(conn, aid, tag_est)
            tags_repo.assign(conn, aid, tag_ilum)
            assets_repo.set_rating(conn, aid, 4)

    # 2. Propriedades personalizadas (EAV)
    prop_forn = properties_repo.create_def(conn, "Fornecedor", "text")
    prop_res = properties_repo.create_def(conn, "Resolução", "text")
    prop_lic = properties_repo.create_def(conn, "Licença", "text")

    for aid in [vaso_id, concreto_id, ceu_id, cadeira_id, madeira_id, torus_id]:
        if aid is not None:
            properties_repo.set_value(conn, aid, prop_forn, "AssetDeck Procedural")
            properties_repo.set_value(conn, aid, prop_res, "1024×1024")
            properties_repo.set_value(conn, aid, prop_lic, "Domínio Público")

    # 3. Coleções manuais (semeadas uma única vez, nomes em pt-BR)
    col_interna = collections_repo.create(conn, "Cena Interna")
    col_casa = collections_repo.create(conn, "Projeto Casa X")
    col_ref = collections_repo.create(conn, "Referências")

    items_interna = [aid for aid in [madeira_id, cadeira_id, vaso_id, concreto_id] if aid]
    collections_repo.add_items(conn, col_interna, items_interna)
    items_casa = [aid for aid in [madeira_id, concreto_id, ceu_id, cadeira_id] if aid]
    collections_repo.add_items(conn, col_casa, items_casa)
    items_ref = [aid for aid in [torus_id, vaso_id, ceu_id] if aid]
    collections_repo.add_items(conn, col_ref, items_ref)

    # 4. Coleções inteligentes (semeadas uma única vez, nomes em pt-BR)
    smart_collections_repo.create(conn, "HDRIs bem avaliados", {"asset_types": ["hdri"], "min_rating": 4})
    smart_collections_repo.create(conn, "Texturas de madeira", {"search": "madeira"})
    smart_collections_repo.create(conn, "Modelos 3D", {"asset_types": ["model"]})
    smart_collections_repo.create(conn, "Materiais PBR", {"asset_types": ["pbr_set"]})

    # 5. Pré-geração de todas as miniaturas no cache
    thumbs_dir = config.thumbs_dir()
    for row in assets:
        cover = row.get("cover_path")
        if cover:
            src = Path(cover)
            key_hash = f"prev-{src.stem}"
        else:
            src = LIB_DIR / row["rel_path"]
            key_hash = row["content_hash"]
        if can_preview(src):
            dest = thumb_path(thumbs_dir, key_hash)
            if not dest.exists():
                make_any_thumbnail(src, dest)

    conn.close()
    print("Dados demo e miniaturas inicializados com sucesso.")


def _optimize_and_save(pixmap, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(".tmp.png")
    ok = pixmap.save(str(temp_path), "PNG")
    if not ok:
        raise RuntimeError(f"Falha ao salvar captura temporária em {temp_path}")

    # Otimização com Pillow: remove canais desnecessários e grava com compactação máxima
    with Image.open(temp_path) as im:
        rgb = im.convert("RGB") if im.mode in ("RGBA", "RGB") else im
        rgb.save(dest, "PNG", optimize=True)
    temp_path.unlink(missing_ok=True)
    print(f"Salvo: {dest.name} ({pixmap.width()}x{pixmap.height()} px)")


def capture_all() -> dict[str, str]:
    """Captura todos os componentes e telas requisitados."""
    results: dict[str, str] = {}
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove capturas descontinuadas se ainda existirem em disco
    for obsoleta in [
        "vitrine-tema-claro.png", "vitrine-tema-escuro.png",
        "detalhes-claro.png", "detalhes-escuro.png",
    ]:
        (DOCS_DIR / obsoleta).unlink(missing_ok=True)

    ensure_gl_format()
    app = QApplication.instance() or QApplication(sys.argv[:1])

    # -----------------------------------------------------------------------
    # 1. Modo Claro: Biblioteca Principal, Sidebar, Busca, Diálogos e Configurações
    # -----------------------------------------------------------------------
    theme.apply_theme(app, theme.Variant(mode="claro"))
    conn = connect(config.db_path())
    win_claro = MainWindow(
        conn=conn, library_root=str(LIB_DIR),
        db_path=config.db_path(), thumbs_dir=config.thumbs_dir(),
    )
    win_claro.resize(1440, 900)
    win_claro._main_splitter.setSizes([260, 840, 340])
    win_claro.sidebar.splitter.setSizes([160, 220, 160, 160])
    win_claro.tags.expandAll()
    win_claro.folders.expandAll()
    win_claro.collections.expandAll()
    win_claro.show()
    app.processEvents()

    # Seleciona o material PBR "Piso Madeira Tabuas" para deixar o painel de detalhes preenchido
    model = win_claro.grid.model()
    target_idx = None
    for r in range(model.rowCount()):
        item_row = model.row_at(model.index(r, 0))
        if item_row:
            nome = item_row.get("name", "").lower()
            rel = item_row.get("rel_path", "").lower()
            if "piso madeira tabuas" in nome or "piso_madeira_tabuas" in rel:
                target_idx = model.index(r, 0)
                break
    if target_idx is None and model.rowCount() > 0:
        target_idx = model.index(0, 0)

    if target_idx is not None:
        win_claro.grid.setCurrentIndex(target_idx)
        win_claro._on_selection(target_idx, QModelIndex())
        win_claro.details.sec_props.set_aberta(True)
        win_claro.details.sec_notas.set_aberta(True)
    win_claro.grid.verticalScrollBar().setValue(0)
    app.processEvents()
    time.sleep(0.15)
    app.processEvents()

    # Biblioteca completa claro com detalhes preenchidos e grade no topo
    _optimize_and_save(win_claro.grab(), DOCS_DIR / "biblioteca-claro.png")
    results["biblioteca-claro.png"] = "OK"

    # Barra lateral de navegação (Pastas, Tags e Coleções sem duplicação)
    _optimize_and_save(win_claro.sidebar.grab(), DOCS_DIR / "colecoes-tags.png")
    results["colecoes-tags.png"] = "OK"

    # Busca com operadores booleanos
    win_claro.search_box.setText("concreto E industrial")
    win_claro._apply_filters()
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()
    _optimize_and_save(win_claro.grab(), DOCS_DIR / "busca-operadores.png")
    results["busca-operadores.png"] = "OK"
    win_claro.search_box.clear()
    win_claro._apply_filters()
    if target_idx is not None:
        win_claro.grid.setCurrentIndex(target_idx)
        win_claro._on_selection(target_idx, QModelIndex())
    win_claro.grid.verticalScrollBar().setValue(0)
    app.processEvents()

    # Janela de Configurações (Modo Claro)
    cfg_dialog = SettingsWindow(win_claro)
    cfg_dialog.resize(800, 540)
    cfg_dialog.show()
    app.processEvents()
    _optimize_and_save(cfg_dialog.grab(), DOCS_DIR / "configuracoes.png")
    results["configuracoes.png"] = "OK"
    cfg_dialog.close()

    # Diálogo de Renomear em lote
    asset_ids = [r["id"] for r in assets_repo.list_for_grid(conn, library_id=1)[:6]]
    rename_dialog = BatchRenameDialog(conn, library_id=1, asset_ids=asset_ids)
    rename_dialog.resize(740, 480)
    rename_dialog.busca_edit.setText("concreto")
    rename_dialog.substitui_edit.setText("cimento_queimado")
    rename_dialog.show()
    app.processEvents()
    _optimize_and_save(rename_dialog.grab(), DOCS_DIR / "renomear-lote.png")
    results["renomear-lote.png"] = "OK"
    rename_dialog.close()

    # Diálogo de Duplicatas
    sample_asset = dict(assets_repo.list_for_grid(conn, library_id=1)[0])
    m1 = {
        "asset_id": sample_asset["id"],
        "name": sample_asset["name"],
        "width": sample_asset["width"] or 1024,
        "height": sample_asset["height"] or 1024,
        "rel_path": sample_asset["rel_path"],
    }
    m2 = {
        "asset_id": 9999,
        "name": sample_asset["name"] + " (cópia reduzida)",
        "width": 512,
        "height": 512,
        "rel_path": "03 - TEXTURAS/copia_reduzida.jpg",
    }
    dup_dialog = DuplicatesDialog(grupos=[[m1, m2]])
    dup_dialog.resize(760, 480)
    dup_dialog.show()
    app.processEvents()
    _optimize_and_save(dup_dialog.grab(), DOCS_DIR / "duplicatas.png")
    results["duplicatas.png"] = "OK"
    dup_dialog.close()

    win_claro.close()
    app.processEvents()

    # -----------------------------------------------------------------------
    # 2. Modo Escuro: Biblioteca Principal e Configurações Escuro
    # -----------------------------------------------------------------------
    theme.apply_theme(app, theme.Variant(mode="escuro"))
    win_escuro = MainWindow(
        conn=conn, library_root=str(LIB_DIR),
        db_path=config.db_path(), thumbs_dir=config.thumbs_dir(),
    )
    win_escuro.resize(1440, 900)
    win_escuro._main_splitter.setSizes([260, 840, 340])
    win_escuro.sidebar.splitter.setSizes([160, 220, 160, 160])
    win_escuro.tags.expandAll()
    win_escuro.folders.expandAll()
    win_escuro.collections.expandAll()
    win_escuro.show()
    app.processEvents()

    model_e = win_escuro.grid.model()
    target_idx_e = None
    for r in range(model_e.rowCount()):
        item_row = model_e.row_at(model_e.index(r, 0))
        if item_row:
            nome = item_row.get("name", "").lower()
            rel = item_row.get("rel_path", "").lower()
            if "piso madeira tabuas" in nome or "piso_madeira_tabuas" in rel:
                target_idx_e = model_e.index(r, 0)
                break
    if target_idx_e is None and model_e.rowCount() > 0:
        target_idx_e = model_e.index(0, 0)

    if target_idx_e is not None:
        win_escuro.grid.setCurrentIndex(target_idx_e)
        win_escuro._on_selection(target_idx_e, QModelIndex())
        win_escuro.details.sec_props.set_aberta(True)
        win_escuro.details.sec_notas.set_aberta(True)
    win_escuro.grid.verticalScrollBar().setValue(0)
    app.processEvents()
    time.sleep(0.15)
    app.processEvents()

    _optimize_and_save(win_escuro.grab(), DOCS_DIR / "biblioteca-escuro.png")
    results["biblioteca-escuro.png"] = "OK"

    # Janela de Configurações (Modo Escuro)
    cfg_dialog_escuro = SettingsWindow(win_escuro)
    cfg_dialog_escuro.resize(800, 540)
    cfg_dialog_escuro.show()
    app.processEvents()
    _optimize_and_save(cfg_dialog_escuro.grab(), DOCS_DIR / "configuracoes-escuro.png")
    results["configuracoes-escuro.png"] = "OK"
    cfg_dialog_escuro.close()

    win_escuro.close()
    app.processEvents()
    conn.close()

    # -----------------------------------------------------------------------
    # 3. Estado Vazio (Primeira execução sem biblioteca)
    # -----------------------------------------------------------------------
    theme.apply_theme(app, theme.Variant(mode="claro"))
    empty_db = DATA_DIR / "empty.db"
    empty_db.unlink(missing_ok=True)
    conn_empty = connect(empty_db)
    apply_migrations(conn_empty)
    win_empty = MainWindow(
        conn=conn_empty, library_root="",
        db_path=empty_db, thumbs_dir=CACHE_DIR / "empty_thumbs",
    )
    win_empty.resize(1440, 900)
    win_empty.show()
    app.processEvents()
    _optimize_and_save(win_empty.grab(), DOCS_DIR / "estado-vazio.png")
    results["estado-vazio.png"] = "OK"
    win_empty.close()
    app.processEvents()
    conn_empty.close()

    # -----------------------------------------------------------------------
    # 4. Visualizadores 3D (HDRI e Modelo 3D Torus)
    # -----------------------------------------------------------------------
    hdri_file = LIB_DIR / "06 - HDRIs" / "ceu_ensolarado_meio_dia.hdr"
    model_file = LIB_DIR / "01 - MODELOS" / "torus.obj"

    xvfb = shutil.which("xvfb-run")
    is_pure_offscreen = (os.environ.get("QT_QPA_PLATFORM") == "offscreen")

    if is_pure_offscreen and xvfb:
        print("Ambiente offscreen detectado: renderizando visualizadores OpenGL via xvfb-run...")
        script_code = f"""
import sys, time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from assetdeck.ui import theme
from assetdeck.ui.hdri_viewer import ensure_gl_format
from assetdeck.ui.viewer_window import VisualizadorWindow

ensure_gl_format()
app = QApplication(sys.argv[:1])
theme.apply_theme(app, theme.Variant(mode='escuro'))

# 1. HDRI
win_hdri = VisualizadorWindow()
win_hdri.resize(1240, 720)
def on_hdri_ready(img):
    def grab_hdri():
        app.processEvents()
        win_hdri.grab().save('{DOCS_DIR / "visualizador-hdri.png"}')
        win_hdri.close()
        # 2. Modelo 3D (Torus com sombreamento suave tridimensional)
        win_model = VisualizadorWindow()
        win_model.resize(1240, 720)
        def on_model_ready(prep):
            def grab_model():
                app.processEvents()
                win_model.grab().save('{DOCS_DIR / "visualizador-modelo-3d.png"}')
                win_model.close()
                app.quit()
            QTimer.singleShot(400, grab_model)
        win_model._sig_modelo.loaded.connect(on_model_ready)
        win_model.abrir_modelo(Path('{model_file}'))
        win_model.show()
    QTimer.singleShot(400, grab_hdri)

win_hdri._sig_hdri.loaded.connect(on_hdri_ready)
win_hdri.abrir_hdri(Path('{hdri_file}'))
win_hdri.show()
app.exec()
"""
        cmd = [
            xvfb, "-a", "-s", "-screen 0 1920x1080x24",
            sys.executable, "-c", script_code
        ]
        proc = subprocess.run(cmd, capture_output=True, env={
            **os.environ,
            "QT_QPA_PLATFORM": "xcb",
            "PYTHONPATH": str(REPO_ROOT),
        })
        if (DOCS_DIR / "visualizador-hdri.png").exists():
            results["visualizador-hdri.png"] = "OK (via xvfb-run)"
        else:
            results["visualizador-hdri.png"] = f"FALHOU ({proc.stderr.decode()[:100]})"

        if (DOCS_DIR / "visualizador-modelo-3d.png").exists():
            results["visualizador-modelo-3d.png"] = "OK (via xvfb-run)"
        else:
            results["visualizador-modelo-3d.png"] = f"FALHOU ({proc.stderr.decode()[:100]})"
    else:
        # Execução direta com eventos
        theme.apply_theme(app, theme.Variant(mode="escuro"))
        v_win = VisualizadorWindow()
        v_win.resize(1240, 720)
        v_win.show()
        app.processEvents()

        # HDRI
        def on_hdri_done(img):
            QTimer.singleShot(300, app.quit)
        v_win._sig_hdri.loaded.connect(on_hdri_done)
        v_win.abrir_hdri(hdri_file)
        app.exec()
        _optimize_and_save(v_win.grab(), DOCS_DIR / "visualizador-hdri.png")
        results["visualizador-hdri.png"] = "OK"

        # Modelo
        def on_model_done(prep):
            QTimer.singleShot(300, app.quit)
        v_win._sig_modelo.loaded.connect(on_model_done)
        v_win.abrir_modelo(model_file)
        app.exec()
        _optimize_and_save(v_win.grab(), DOCS_DIR / "visualizador-modelo-3d.png")
        results["visualizador-modelo-3d.png"] = "OK"
        v_win.close()

    return results


def main() -> int:
    print("Iniciando rotina de screenshots determinística...")
    setup_demo_data()
    results = capture_all()
    print("\n--- Resumo das capturas ---")
    for name, status in results.items():
        print(f"  {name:30s} -> {status}")
    print("Capturas concluídas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
