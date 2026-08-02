"""Cria/atualiza a entrada do AssetDeck no menu de aplicativos do Zorin.

Roda uma vez (ou de novo, se você mover a pasta do projeto): gera
~/.local/share/applications/assetdeck.desktop com os caminhos ABSOLUTOS
desta máquina — não dá pra versionar esse arquivo no repo porque ele muda
por instalação (por isso o script, e não um .desktop pronto no git).

Uso:
    source .venv/bin/activate && python install_desktop_entry.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ICON_PATH = PROJECT_ROOT / "assetdeck" / "ui" / "icons" / "app-icon.png"
DEST = Path.home() / ".local" / "share" / "applications" / "assetdeck.desktop"

TEMPLATE = """[Desktop Entry]
Type=Application
Name=AssetDeck
Comment=Gerenciador de assets local, integrado ao Blender
Exec="{python}" -m assetdeck
Path={project_root}
Icon={icon}
Terminal=false
Categories=Graphics;3DGraphics;
StartupNotify=true
"""


def main() -> int:
    if not ICON_PATH.exists():
        print(f"Ícone não encontrado em {ICON_PATH} — rode a partir da raiz do projeto.")
        return 1

    conteudo = TEMPLATE.format(
        python=sys.executable,  # o Python DESTE venv, ativado ou não
        project_root=PROJECT_ROOT,
        icon=ICON_PATH,
    )

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(conteudo, encoding="utf-8")
    DEST.chmod(0o755)
    print(f"Escrito em {DEST}")

    validador = shutil.which("desktop-file-validate")
    if validador:
        subprocess.run([validador, str(DEST)], check=False)

    atualizador = shutil.which("update-desktop-database")
    if atualizador:
        subprocess.run([atualizador, str(DEST.parent)], check=False)
        print("Cache do menu de aplicativos atualizado.")
    else:
        print("update-desktop-database não encontrado — o GNOME escaneia "
              "essa pasta sozinho de qualquer forma, pode levar alguns "
              "segundos a mais para aparecer.")

    print("Pronto — procure 'AssetDeck' no menu de aplicativos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
