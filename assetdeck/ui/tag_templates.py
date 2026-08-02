"""Templates de tags prontos (Fatia 35).

Montar à mão uma árvore que dê conta de uma biblioteca de arquitetura são
dezenas de tags, cada uma com nome, cor e ícone — chato o bastante para
nunca ser feito. Aqui a estrutura vem pronta.

Os três níveis são **o mesmo tronco podado em profundidades diferentes**,
não três listas soltas: aplicar o "balanceado" depois do "resumido" só
acrescenta folhas, sem duplicar nada.

Aplicar SOMA, nunca substitui: `tags_repo.create()` devolve a tag
existente sem tocar em cor, ícone ou nos assets já marcados.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import NamedTuple

from assetdeck.db.repos import tags as tags_repo

log = logging.getLogger(__name__)

RESUMIDO = "resumido"
BALANCEADO = "balanceado"
COMPLETO = "completo"

NIVEIS: tuple[tuple[str, str, int], ...] = (
    (RESUMIDO, "Resumido", 1),
    (BALANCEADO, "Balanceado", 2),
    (COMPLETO, "Completo", 3),
)

# Cor por categoria-raiz. É DADO DO USUÁRIO (tag), não UI de sistema —
# não fere a regra monocromática do tema, que vale para botões e painéis.
TERRA = "#8A6A4F"
VERDE = "#4A7A4A"
ROXO = "#7A5A8A"
AMBAR = "#C08A2E"
AZUL = "#4A6B8A"
PETROLEO = "#3F7A7A"
CINZA = "#7A7A84"
AREIA = "#A08558"


class No(NamedTuple):
    nome: str
    icone: str | None = None
    cor: str | None = None          # None = herda a do pai
    filhos: tuple["No", ...] = ()


# O tronco completo. Cada nível de profundidade é uma poda deste mesmo
# desenho — ver `arvore(nivel)`.
ARQUITETURA: tuple[No, ...] = (
    No("Materiais", "tag-metal", TERRA, (
        No("Madeira", "tag-madeira", "#8A5A2E", (
            No("Carvalho"), No("Nogueira"), No("Pinho"),
            No("Ripado"), No("Compensado"),
        )),
        No("Metal", "tag-metal", "#5A7A96", (
            No("Aço"), No("Alumínio"), No("Cobre"),
            No("Corten"), No("Ferro"),
        )),
        No("Pedra", "tag-pedra", "#7A7A80", (
            No("Mármore"), No("Granito"), No("Travertino"), No("Ardósia"),
        )),
        No("Concreto", "tag-concreto", "#8A8A8A", (
            No("Aparente"), No("Texturizado"),
        )),
        No("Tijolo", "tag-tijolo", "#9A5A44"),
        No("Vidro", "tag-vidro", "#6A9AA8"),
        No("Tecido", "tag-tecido", "#9A6A7A", (
            No("Estofado"), No("Cortina"), No("Tapete"),
        )),
        No("Cerâmica", "tag-ceramica", "#A87A5A", (
            No("Porcelanato"), No("Azulejo"),
        )),
        No("Couro", "tag-couro", "#7A5340"),
    )),
    No("Vegetação", "tag-arvore", VERDE, (
        No("Árvores", "tag-arvore", None, (
            No("Caducifólia"), No("Perene"), No("Palmeira"),
        )),
        No("Arbustos", "tag-arbusto"),
        No("Flores", "tag-flor"),
        No("Grama", "tag-grama"),
        No("Plantas de interior", "tag-planta"),
        No("Forração", "tag-folha"),
    )),
    No("Mobiliário", "tag-movel", ROXO, (
        No("Assentos", None, None, (
            No("Cadeira"), No("Poltrona"), No("Sofá"), No("Banco"),
        )),
        No("Mesas", None, None, (
            No("Jantar"), No("Centro"), No("Escritório"), No("Lateral"),
        )),
        No("Camas"),
        No("Armazenamento", None, None, (
            No("Armário"), No("Estante"), No("Cômoda"),
        )),
        No("Luminárias", "tag-luz"),
        No("Decoração"),
    )),
    No("Iluminação", "tag-luz", AMBAR, (
        No("HDRI", None, None, (
            No("Céu limpo"), No("Nublado"), No("Entardecer"),
            No("Noite"), No("Interior"), No("Estúdio"),
        )),
        No("IES"),
        No("Natural"),
        No("Artificial"),
    )),
    No("Escala", "tag-camera", AZUL, (
        No("Pessoas", None, None, (
            No("Silhueta"), No("Recortada"), No("3D"),
        )),
        No("Veículos", None, None, (
            No("Carro"), No("Bicicleta"), No("Utilitário"),
        )),
        No("Animais"),
    )),
    No("Ambiente", "tag-planta", PETROLEO, (
        No("Interior", None, None, (
            No("Residencial"), No("Comercial"), No("Corporativo"),
        )),
        No("Exterior", None, None, (
            No("Fachada"), No("Paisagismo"), No("Cobertura"),
        )),
        No("Urbano"),
        No("Rural"),
    )),
    No("Acabamento", "tag-espelho", CINZA, (
        No("Fosco"),
        No("Brilhante"),
        No("Texturizado"),
        No("Liso"),
        No("Translúcido"),
    )),
    No("Referência", "tag-papel", AREIA, (
        No("Projeto"), No("Moodboard"), No("Detalhe construtivo"),
        No("Catálogo"),
    )),
)


def arvore(nivel: str) -> tuple[No, ...]:
    """O tronco podado na profundidade do nível."""
    profundidade = dict((k, p) for k, _, p in NIVEIS).get(nivel)
    if profundidade is None:
        raise ValueError(f"Nível de template desconhecido: {nivel!r}")
    return _podar(ARQUITETURA, profundidade)


def _podar(nos: tuple[No, ...], restante: int) -> tuple[No, ...]:
    if restante <= 0:
        return ()
    return tuple(n._replace(filhos=_podar(n.filhos, restante - 1)) for n in nos)


def contar(nos: tuple[No, ...]) -> int:
    return sum(1 + contar(n.filhos) for n in nos)


class Resultado(NamedTuple):
    criadas: int
    existentes: int


def aplicar(conn: sqlite3.Connection, nivel: str) -> Resultado:
    """Cria o que falta e reaproveita o que já existe.

    Nunca sobrescreve: uma tag com o mesmo nome no mesmo pai mantém a cor,
    o ícone e os assets que o Rafael já tinha posto nela.
    """
    criadas = existentes = 0
    fila: list[tuple[No, int | None, str | None]] = [
        (n, None, None) for n in arvore(nivel)
    ]
    while fila:
        no, pai_id, cor_herdada = fila.pop(0)
        cor = no.cor or cor_herdada
        if _existe(conn, no.nome, pai_id):
            existentes += 1
        else:
            criadas += 1
        tag_id = tags_repo.create(conn, no.nome, parent_id=pai_id,
                                  color=cor, icon=no.icone)
        fila.extend((f, tag_id, cor) for f in no.filhos)

    log.info("Template de tags %r aplicado: %d criadas, %d já existiam.",
             nivel, criadas, existentes)
    return Resultado(criadas, existentes)


def previa(conn: sqlite3.Connection, nivel: str) -> list[tuple[No, int, str | None, bool]]:
    """(nó, profundidade, cor efetiva, já existe?) em ordem de árvore —
    alimenta a pré-visualização do diálogo sem tocar no banco."""
    saida: list[tuple[No, int, str | None, bool]] = []

    def caminhar(nos: tuple[No, ...], nivel_prof: int, pai_id: int | None,
                 cor_herdada: str | None) -> None:
        for no in nos:
            cor = no.cor or cor_herdada
            tag_id = _id_de(conn, no.nome, pai_id)
            saida.append((no, nivel_prof, cor, tag_id is not None))
            caminhar(no.filhos, nivel_prof + 1, tag_id, cor)

    caminhar(arvore(nivel), 0, None, None)
    return saida


def _id_de(conn: sqlite3.Connection, nome: str, pai_id: int | None) -> int | None:
    row = conn.execute(
        "SELECT id FROM tags WHERE name = ? AND parent_id IS ? AND deleted_at IS NULL",
        (nome, pai_id),
    ).fetchone()
    return row["id"] if row else None


def _existe(conn: sqlite3.Connection, nome: str, pai_id: int | None) -> bool:
    return _id_de(conn, nome, pai_id) is not None
