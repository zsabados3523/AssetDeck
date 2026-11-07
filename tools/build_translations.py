#!/usr/bin/env python3
"""Utilitário para atualizar e compilar arquivos de tradução (.ts -> .qm).

Uso:
    python tools/build_translations.py           # atualiza .ts e compila .qm
    python tools/build_translations.py --update  # apenas extrai/atualiza .ts
    python tools/build_translations.py --release # apenas compila .qm
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = ROOT / "translations"
SOURCE_DIR = ROOT / "assetdeck"


def find_tool(name: str) -> Path:
    """Localiza um executável da toolchain Qt (lupdate, lrelease)."""
    candidates = [
        Path(sys.executable).parent / name,
        Path(sys.executable).parent / f"pyside6-{name}",
        ROOT / ".venv" / "bin" / name,
        ROOT / ".venv" / "bin" / f"pyside6-{name}",
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c

    which_pyside = shutil.which(f"pyside6-{name}")
    if which_pyside:
        return Path(which_pyside)

    which_qt = shutil.which(name)
    if which_qt:
        return Path(which_qt)

    raise FileNotFoundError(
        f"Ferramenta Qt '{name}' (ou 'pyside6-{name}') não encontrada. "
        "Certifique-se de que o PySide6 está instalado no ambiente virtual."
    )


def update_translations(lang: str, no_obsolete: bool = False) -> Path:
    """Executa lupdate para extrair strings translatáveis de assetdeck/."""
    lupdate = find_tool("lupdate")
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts_file = TRANSLATIONS_DIR / f"assetdeck_{lang}.ts"

    cmd = [
        str(lupdate),
        "-extensions", "py",
        "-source-language", "pt_BR",
        "-target-language", lang,
    ]
    if no_obsolete:
        cmd.append("-no-obsolete")
    cmd.extend([str(SOURCE_DIR), "-ts", str(ts_file)])

    print(f"Executando lupdate: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    return ts_file


def release_translations(lang: str) -> Path:
    """Executa lrelease para compilar o arquivo .ts em .qm binário."""
    lrelease = find_tool("lrelease")
    ts_file = TRANSLATIONS_DIR / f"assetdeck_{lang}.ts"
    if not ts_file.exists():
        raise FileNotFoundError(f"Arquivo de tradução não encontrado: {ts_file}")

    qm_file = TRANSLATIONS_DIR / f"assetdeck_{lang}.qm"
    cmd = [
        str(lrelease),
        str(ts_file),
        "-qm", str(qm_file),
    ]

    print(f"Executando lrelease: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    return qm_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Atualiza e compila arquivos de tradução do AssetDeck.")
    parser.add_argument("--update", action="store_true", help="Atualiza arquivos .ts a partir do código.")
    parser.add_argument("--release", action="store_true", help="Compila arquivos .ts em .qm.")
    parser.add_argument("--lang", default="en", help="Código do idioma (padrão: en).")
    parser.add_argument("--no-obsolete", action="store_true", help="Remove strings obsoletas ao atualizar.")
    args = parser.parse_args()

    do_update = args.update
    do_release = args.release
    if not do_update and not do_release:
        do_update = True
        do_release = True

    try:
        if do_update:
            ts = update_translations(args.lang, no_obsolete=args.no_obsolete)
            print(f"Traduções atualizadas com sucesso: {ts}")
        if do_release:
            qm = release_translations(args.lang)
            print(f"Arquivo compilado com sucesso: {qm}")
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
