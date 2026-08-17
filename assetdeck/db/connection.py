"""Conexão SQLite: WAL, foreign keys ligadas, timeouts amigáveis."""

from __future__ import annotations

import colorsys
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

# Abaixo disto a cor não tem matiz utilizável: é cinza/branco/preto. Separar
# acromático de colorido é o que impede "Cinza" de trazer folhagem e "Verde"
# de trazer concreto (Fatia 76).
_SATURACAO_MINIMA = 0.15

# Pesos da distância perceptual. O MATIZ manda — é ele que responde "isto é
# verde?" —, e saturação/brilho entram só como desempate. Calibrados contra
# arquivos reais da testlib (folhagem fotográfica: #4f6338, #7e8d70) de forma
# que caiam dentro de `COLOR_TOLERANCE` do verde da paleta, e o amarelo fique
# de fora.
_PESO_MATIZ = 1.8      # por grau de diferença no círculo de cor (0..180)
_PESO_SATURACAO = 40.0
_PESO_BRILHO = 60.0

# Famílias diferentes (uma acromática, outra não) nunca casam.
_INCOMPATIVEL = 999.0


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_distance(hex_a: str | None, hex_b: str | None) -> float | None:
    """Distância PERCEPTUAL entre duas cores em hex, para o filtro de busca
    por cor (Fatia 39, refeita na Fatia 76).

    Era distância euclidiana em RGB, e por isso o filtro não servia pra nada:
    o Rafael relatou "clico para filtrar por cor verde e as texturas de folha
    nem aparecem". Medido na biblioteca dele — folha real é verde-oliva
    DESSATURADO (`#4f6338`, `#7e8d70`), o verde da paleta era vivo
    (`#27ae60`), e em RGB isso dá ~94 contra uma tolerância de 90. Passava
    raspando: "Verde" e "Amarelo" devolviam ZERO assets numa biblioteca cheia
    de folhagem.

    O problema é a métrica, não a tolerância: em RGB, escurecer uma cor
    afasta tanto quanto trocar de matiz, então nenhuma tolerância separa
    "verde escuro" de "vermelho claro" sem também deixar tudo entrar. Aqui a
    comparação é em HSV, com o MATIZ pesando muito mais que brilho e
    saturação — que é como uma pessoa responde "isso aí é verde".

    Devolve `None` se qualquer lado não tiver cor calculada (arquivo
    não-raster) ou vier corrompido — o filtro trata como "não bate" e nunca
    derruba a consulta inteira.
    """
    if hex_a is None or hex_b is None:
        return None
    try:
        r1, g1, b1 = _hex_to_rgb(hex_a)
        r2, g2, b2 = _hex_to_rgb(hex_b)
    except (ValueError, TypeError):
        log.warning("Cor em hex inválida no banco ao comparar %r com %r", hex_a, hex_b)
        return None

    h1, s1, v1 = colorsys.rgb_to_hsv(r1 / 255, g1 / 255, b1 / 255)
    h2, s2, v2 = colorsys.rgb_to_hsv(r2 / 255, g2 / 255, b2 / 255)

    cinza1 = s1 < _SATURACAO_MINIMA
    cinza2 = s2 < _SATURACAO_MINIMA
    if cinza1 != cinza2:
        return _INCOMPATIVEL
    if cinza1:
        # Sem matiz dos dois lados: o que resta é claro/escuro. É assim que
        # "Branco", "Cinza" e "Preto" se distinguem entre si.
        return abs(v1 - v2) * 300.0

    # Matiz é circular: 350° e 10° são vizinhos, não opostos.
    dh = abs(h1 - h2) * 360.0
    dh = min(dh, 360.0 - dh)
    return dh * _PESO_MATIZ + abs(s1 - s2) * _PESO_SATURACAO + abs(v1 - v2) * _PESO_BRILHO


def connect(db_path: Path) -> sqlite3.Connection:
    """Abre (ou cria) o banco com os pragmas do projeto.

    - WAL: leitura concorrente com escrita (UI lê enquanto o indexer grava).
    - foreign_keys ON: o SQLite só valida FKs se pedirmos explicitamente.
    - busy_timeout: espera em vez de falhar se outra thread estiver escrevendo.
    - color_distance: função SQL customizada pro filtro de busca por cor
      (Fatia 39) — comparar hex vira aritmética, não dá pra fazer só com
      SQL puro sem ficar ilegível.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.create_function("color_distance", 2, _color_distance, deterministic=True)
    log.debug("Banco aberto em %s", db_path)
    return conn
