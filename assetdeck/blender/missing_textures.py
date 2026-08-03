"""Lista texturas com caminho quebrado dentro de um .blend (Fatia 40).

Mesmo padrão de render.py::render_thumbnail (subprocess do Blender
headless, timeout, nunca levanta) — mas isto é SÓ LEITURA: nunca escreve
no .blend do usuário nem em nenhum outro arquivo.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from assetdeck.blender.render import TIMEOUT_S, blender_command

log = logging.getLogger(__name__)

_MARCADOR = "ASSETDECK_TEXTURAS_JSON "


def script_path() -> Path:
    return Path(__file__).parent / "scripts" / "list_missing_textures.py"


@dataclass
class MissingTexturesResult:
    ok: bool
    perdidas: list[dict] = field(default_factory=list)  # [{"nome", "caminho_esperado"}]
    recuperadas_auto: int = 0
    erro: str | None = None


def list_missing_textures(blend_path: Path,
                          comando: list[str] | None = None) -> MissingTexturesResult:
    """Roda o Blender headless nesse .blend e devolve o que continua
    quebrado DEPOIS da relocalização automática (a mesma que o render já
    faz) — não o cru. Nunca levanta: devolve o resultado."""
    cmd_base = comando or blender_command()
    if cmd_base is None:
        return MissingTexturesResult(False, erro="Blender não encontrado nesta máquina.")
    if not blend_path.is_file():
        return MissingTexturesResult(False, erro=f"Arquivo não existe: {blend_path}")

    cmd = [*cmd_base, "-b", "-P", str(script_path()), "--", str(blend_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return MissingTexturesResult(False, erro=f"Passou de {TIMEOUT_S}s (arquivo pesado).")
    except OSError as exc:
        return MissingTexturesResult(False, erro=f"Falha ao executar o Blender: {exc}")

    for linha in (proc.stdout or "").splitlines():
        if linha.startswith(_MARCADOR):
            dados = json.loads(linha[len(_MARCADOR):])
            return MissingTexturesResult(True, perdidas=dados["perdidas"],
                                         recuperadas_auto=dados["recuperadas_auto"])

    log.error("Checagem de texturas falhou para %s: %s", blend_path.name,
              (proc.stderr or proc.stdout or "").strip()[-1500:])
    return MissingTexturesResult(
        False, erro="Não consegui ler o resultado do Blender (ver log).")
