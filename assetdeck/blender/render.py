"""Renderiza capas de modelos chamando o Blender em modo headless.

Roda fora da UI (thread) e um modelo por vez: cada render é um processo
Blender separado, então um .blend problemático nunca derruba o AssetDeck.

Lembrete do sandbox (descoberto no F2): o Flatpak tem /tmp próprio, então
tudo é escrito em ~/.local/share/assetdeck, que ele enxerga.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

FLATPAK_APP = "org.blender.Blender"
TIMEOUT_S = 180  # um modelo pesado não pode travar a fila para sempre


def script_path() -> Path:
    return Path(__file__).parent / "scripts" / "render_thumb.py"


def blender_command() -> list[str] | None:
    """Como invocar o Blender nesta máquina, ou None se não houver.

    Preferência: Flatpak (é o que o Rafael usa) → binário no PATH.
    """
    if shutil.which("flatpak"):
        try:
            saida = subprocess.run(
                ["flatpak", "info", FLATPAK_APP],
                capture_output=True, timeout=15, check=False,
            )
            if saida.returncode == 0:
                return ["flatpak", "run", FLATPAK_APP]
        except (OSError, subprocess.SubprocessError):
            log.warning("Não consegui consultar o Flatpak.", exc_info=True)
    binario = shutil.which("blender")
    return [binario] if binario else None


@dataclass
class RenderResult:
    ok: bool
    dest: Path | None = None
    erro: str | None = None


def render_thumbnail(blend_path: Path, dest: Path, size: int = 512,
                     comando: list[str] | None = None) -> RenderResult:
    """Renderiza a capa de um .blend. Nunca levanta: devolve o resultado."""
    cmd_base = comando or blender_command()
    if cmd_base is None:
        return RenderResult(False, erro="Blender não encontrado nesta máquina.")
    if not blend_path.is_file():
        return RenderResult(False, erro=f"Arquivo não existe: {blend_path}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*cmd_base, "-b", "-P", str(script_path()), "--",
           str(blend_path), str(dest), str(size)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return RenderResult(False, erro=f"Render passou de {TIMEOUT_S}s (modelo pesado).")
    except OSError as exc:
        return RenderResult(False, erro=f"Falha ao executar o Blender: {exc}")

    if dest.is_file() and dest.stat().st_size > 0:
        return RenderResult(True, dest=dest)

    log.error("Render falhou para %s: %s", blend_path.name,
              (proc.stderr or proc.stdout or "").strip()[-1500:])
    return RenderResult(False, erro=_motivo(proc))


def _motivo(proc) -> str:
    """Mensagem curta e útil a partir da saída do Blender.

    Prefere a linha da exceção (última do traceback) ou um 'Error:' do
    Blender — não uma linha qualquer de contexto, que confunde mais do que
    ajuda quando o Rafael cola o erro de volta.
    """
    texto = (proc.stderr or "") + "\n" + (proc.stdout or "")
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    for ln in reversed(linhas):
        if ln.startswith(("Error:", "OSError", "RuntimeError", "SystemExit")):
            return ln
    excecoes = [ln for ln in linhas if ln.split(":")[0].endswith("Error")]
    if excecoes:
        return excecoes[-1]
    return linhas[-1] if linhas else f"código {proc.returncode}"


def models_without_cover(conn, library_id: int, library_root: Path) -> list[tuple]:
    """(asset_id, nome, caminho absoluto) dos modelos que ainda não têm capa."""
    linhas = conn.execute(
        """SELECT a.id, a.name, f.rel_path
           FROM assets a JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
             AND a.asset_type IN ('model', 'scene')
             AND f.missing_since IS NULL
             AND LOWER(f.rel_path) LIKE '%.blend'
             AND NOT EXISTS (SELECT 1 FROM previews p
                             WHERE p.asset_id = a.id AND p.is_cover = 1
                               AND p.deleted_at IS NULL)
           ORDER BY a.name COLLATE NOCASE""",
        (library_id,),
    ).fetchall()
    return [(r["id"], r["name"], library_root / r["rel_path"]) for r in linhas]
