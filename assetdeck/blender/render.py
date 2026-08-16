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

# Cena de hoje, hardcoded — vira o default de render_thumbnail() (Fatia 38).
# Continua igual pra quem chama sem passar nada (inclusive os testes atuais).
BG_COLOR_PADRAO = (0.30, 0.30, 0.32)
BG_STRENGTH_PADRAO = 1.8
SUN_ENERGY_PADRAO = 3.0


def hex_to_linear_rgb(hex_str: str) -> tuple[float, float, float]:
    """'#RRGGBB' (sRGB, o que sai do QColorDialog) → RGB linear (o que o
    shader do Blender espera). Sem isso a cor escolhida sai mais clara do
    que o Rafael viu na amostra."""
    hex_str = hex_str.lstrip("#")
    canais = (int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _srgb_para_linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return tuple(_srgb_para_linear(c) for c in canais)


def script_path() -> Path:
    return Path(__file__).parent / "scripts" / "render_thumb.py"


def export_obj_script_path() -> Path:
    return Path(__file__).parent / "scripts" / "export_obj.py"


def blender_command() -> list[str] | None:
    """Como invocar o Blender nesta máquina, ou None se não houver.

    Preferência: Flatpak (se instalado) → binário no PATH (instalação
    padrão/portátil, o que o Rafael usa hoje).
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
                     comando: list[str] | None = None,
                     bg_color: tuple[float, float, float] = BG_COLOR_PADRAO,
                     bg_strength: float = BG_STRENGTH_PADRAO,
                     sun_energy: float = SUN_ENERGY_PADRAO) -> RenderResult:
    """Renderiza a capa de um .blend. Nunca levanta: devolve o resultado.

    `bg_color`/`bg_strength`/`sun_energy` já em LINEAR (converta hex do
    config com `hex_to_linear_rgb` antes de chamar) — cena configurável
    da Fatia 38, defaults iguais ao que já era hardcoded.
    """
    cmd_base = comando or blender_command()
    if cmd_base is None:
        return RenderResult(False, erro="Blender não encontrado nesta máquina.")
    if not blend_path.is_file():
        return RenderResult(False, erro=f"Arquivo não existe: {blend_path}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*cmd_base, "-b", "--factory-startup", "-P", str(script_path()), "--",
           str(blend_path), str(dest), str(size),
           str(bg_color[0]), str(bg_color[1]), str(bg_color[2]),
           str(bg_strength), str(sun_energy)]
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


def export_to_obj(blend_path: Path, dest: Path,
                  comando: list[str] | None = None) -> RenderResult:
    """Exporta a geometria de um .blend pra .obj, chamando o Blender
    headless — é assim que o visualizador 3D (Fase 6) "lê" um .blend, já
    que o formato binário dele não tem parser de terceiros confiável (só
    o próprio Blender sabe ler de verdade). Nunca levanta: devolve o
    resultado, mesmo padrão de `render_thumbnail`.

    Quem chama é responsável por cachear (`model3d/blend_loader.py`) —
    esta função sempre roda o Blender de novo, não confere se já existe.
    """
    cmd_base = comando or blender_command()
    if cmd_base is None:
        return RenderResult(False, erro="Blender não encontrado nesta máquina.")
    if not blend_path.is_file():
        return RenderResult(False, erro=f"Arquivo não existe: {blend_path}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*cmd_base, "-b", "--factory-startup", "-P", str(export_obj_script_path()), "--",
           str(blend_path), str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return RenderResult(False, erro=f"Exportação passou de {TIMEOUT_S}s (modelo pesado).")
    except OSError as exc:
        return RenderResult(False, erro=f"Falha ao executar o Blender: {exc}")

    if dest.is_file() and dest.stat().st_size > 0:
        return RenderResult(True, dest=dest)

    log.error("Exportação pra .obj falhou para %s: %s", blend_path.name,
              (proc.stderr or proc.stdout or "").strip()[-1500:])
    return RenderResult(False, erro=_motivo(proc))


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
