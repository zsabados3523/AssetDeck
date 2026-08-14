"""Templates de tags prontos (Fatia 35, generalizado na Fatia 55).

Montar à mão uma árvore que dê conta de uma biblioteca inteira são dezenas
de tags, cada uma com nome, cor e ícone — chato o bastante para nunca ser
feito. Aqui a estrutura vem pronta, um TEMPLATE por área de trabalho
(Arquitetura, Propaganda, Construção...).

Dentro de cada template, os três níveis são **o mesmo tronco podado em
profundidades diferentes**, não três listas soltas: aplicar o
"balanceado" depois do "resumido" só acrescenta folhas, sem duplicar nada.

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

# ---- Propaganda/Publicidade (Fatia 55) ----
PROPAGANDA: tuple[No, ...] = (
    No("Formato", "tag-papel", AMBAR, (
        No("Anúncio impresso"), No("Banner digital"), No("Vídeo/Comercial"),
        No("Social media", None, None, (
            No("Stories"), No("Feed"), No("Reels/Shorts"),
        )),
        No("Outdoor"),
    )),
    No("Mídia", "tag-camera", AZUL, (
        No("Still"), No("Motion"), No("3D render"), No("Mockup"),
    )),
    No("Produto/Cena", "tag-movel", ROXO, (
        No("Embalagem"), No("Produto em cena"), No("Still life"), No("Cenário/set"),
    )),
    No("Elementos gráficos", "tag-pincel", PETROLEO, (
        No("Logo/Marca"), No("Tipografia"), No("Ícone"), No("Textura de fundo"),
    )),
    No("Iluminação/Estúdio", "tag-luz", TERRA, (
        No("Softbox"), No("Fundo infinito"), No("Ring light"),
        No("HDRI de estúdio"),
    )),
    No("Composição/Câmera", "tag-camera", VERDE, (
        No("Ângulo baixo"), No("Close-up"), No("Plano aberto"), No("Simetria"),
    )),
    No("Estilo", "tag-espelho", CINZA, (
        No("Minimalista"), No("Vibrante"), No("Corporativo"), No("Luxo"),
        No("Retrô"),
    )),
    No("Referência", "tag-papel", AREIA, (
        No("Moodboard"), No("Briefing"), No("Cliente"),
    )),
)

# ---- Construção (Fatia 55) ----
CONSTRUCAO: tuple[No, ...] = (
    No("Materiais de construção", "tag-concreto", TERRA, (
        No("Cimento/Argamassa"), No("Tijolo/Bloco"), No("Aço estrutural"),
        No("Madeira de obra"), No("Telha"), No("Impermeabilizante"),
    )),
    No("Equipamentos/Maquinário", "tag-metal", CINZA, (
        No("Escavadeira"), No("Guindaste"), No("Betoneira"),
        No("Andaime"), No("Empilhadeira"),
    )),
    No("Estrutura", "tag-tijolo", AZUL, (
        No("Fundação"), No("Laje"), No("Pilar"), No("Viga"),
        No("Alvenaria"), No("Cobertura"),
    )),
    No("Canteiro de obras", "tag-bandeira", AREIA, (
        No("Tapume"), No("Container"), No("Sinalização"), No("Depósito"),
    )),
    No("EPI/Segurança", "tag-alerta", AMBAR, (
        No("Capacete"), No("Colete"), No("Bota"), No("Cinto de segurança"),
    )),
    No("Instalações", "tag-luz", PETROLEO, (
        No("Elétrica"), No("Hidráulica"), No("HVAC"), No("Gás"),
    )),
    No("Documentação técnica", "tag-papel", ROXO, (
        No("Planta baixa"), No("Corte"), No("Detalhe construtivo"), No("Memorial"),
    )),
    No("Fases da obra", "tag-estrela", VERDE, (
        No("Terraplenagem"), No("Estrutural"), No("Acabamento"), No("Entrega"),
    )),
)

# ---- Filme & Animação (Fatia 55) ----
FILME_ANIMACAO: tuple[No, ...] = (
    No("Cenário/Set", "tag-movel", TERRA, (
        No("Interior"), No("Exterior"), No("Estúdio virtual"), No("Matte painting"),
    )),
    No("Personagem/Prop", "tag-estrela", ROXO, (
        No("Rig"), No("Vestuário"), No("Adereço"), No("Veículo de cena"),
    )),
    No("Câmera", "tag-camera", AZUL, (
        No("Lente"), No("Movimento de câmera"), No("Ângulo"),
        No("Profundidade de campo"),
    )),
    No("Iluminação", "tag-luz", AMBAR, (
        No("Três pontos"), No("Prática"), No("HDRI de locação"), No("Contraluz"),
    )),
    No("Efeitos", "tag-alerta", PETROLEO, (
        No("Partículas"), No("Fumaça/Fogo"), No("Destruição"),
        No("Fluido"), No("Simulação de tecido"),
    )),
    No("Pós-produção", "tag-pincel", CINZA, (
        No("Color grading"), No("Compositing"), No("LUT"), No("Grão de filme"),
    )),
    No("Gênero/Estilo", "tag-bandeira", VERDE, (
        No("Drama"), No("Ação"), No("Ficção científica"),
        No("Animação 2D"), No("Stop motion"),
    )),
    No("Referência", "tag-papel", AREIA, (
        No("Storyboard"), No("Shotlist"), No("Continuidade"),
    )),
)

# ---- Game Dev (Fatia 55) ----
GAMEDEV: tuple[No, ...] = (
    No("Categoria de asset", "tag-movel", ROXO, (
        No("Prop"), No("Terreno/Environment"), No("Personagem"),
        No("Arma"), No("UI/HUD"), No("VFX"),
    )),
    No("Engine/Pipeline", "tag-metal", CINZA, (
        No("Unreal"), No("Unity"), No("Godot"), No("Substance"),
    )),
    No("Nível técnico", "tag-estrela", AZUL, (
        No("Low poly"), No("High poly (baked)"), No("PBR"),
        No("Rigged"), No("Animado"),
    )),
    No("Estilo visual", "tag-pincel", AMBAR, (
        No("Realista"), No("Stylized"), No("Cartoon"),
        No("Pixel art"), No("Low poly art"),
    )),
    No("Gameplay", "tag-bandeira", VERDE, (
        No("Interativo"), No("Colecionável"), No("Obstáculo"), No("Colisão"),
    )),
    No("Otimização", "tag-alerta", PETROLEO, (
        No("LOD"), No("Texture atlas"), No("Occlusion"), No("Draw call"),
    )),
    No("Plataforma", "tag-espelho", TERRA, (
        No("PC"), No("Mobile"), No("Console"), No("VR/AR"),
    )),
    No("Referência", "tag-papel", AREIA, (
        No("Concept art"), No("Style guide"),
    )),
)

# ---- Design de Produto (Fatia 55 — proposta) ----
DESIGN_PRODUTO: tuple[No, ...] = (
    No("Tipo de produto", "tag-movel", ROXO, (
        No("Eletrônico"), No("Mobiliário"), No("Utensílio"),
        No("Embalagem"), No("Wearable"),
    )),
    No("Material/Acabamento", "tag-plastico", TERRA, (
        No("Plástico injetado"), No("Metal usinado"), No("Vidro"),
        No("Silicone"), No("Fosco/Brilhante"),
    )),
    No("Processo de fabricação", "tag-metal", CINZA, (
        No("Impressão 3D"), No("Injeção"), No("Usinagem CNC"), No("Corte a laser"),
    )),
    No("Embalagem", "tag-papel", AREIA, (
        No("Caixa"), No("Blister"), No("Rótulo"), No("Unboxing"),
    )),
    No("Ergonomia/Escala", "tag-estrela", AZUL, (
        No("Mão"), No("Corpo"), No("Ambiente de uso"),
    )),
    No("Renderização", "tag-camera", PETROLEO, (
        No("Estúdio de produto"), No("Explodido"), No("Corte técnico"),
    )),
    No("Estilo", "tag-espelho", AMBAR, (
        No("Minimalista"), No("Industrial"), No("Orgânico"),
    )),
    No("Referência", "tag-papel", VERDE, (
        No("Moodboard"), No("Concorrente"), No("Patente"),
    )),
)

# ---- VFX & Simulação (Fatia 55 — proposta) ----
VFX_SIMULACAO: tuple[No, ...] = (
    No("Tipo de efeito", "tag-alerta", AMBAR, (
        No("Explosão"), No("Fumaça"), No("Fogo"), No("Água"),
        No("Destruição"), No("Magia/Energia"),
    )),
    No("Simulação física", "tag-metal", CINZA, (
        No("Rígida"), No("Tecido"), No("Fluido"), No("Cabelo/Pelo"), No("Softbody"),
    )),
    No("Partículas", "tag-estrela", AZUL, (
        No("Emissor"), No("Força/Campo"), No("Colisão"), No("Instância"),
    )),
    No("Ambiente/Elemento", "tag-folha", VERDE, (
        No("Poeira"), No("Névoa"), No("Faísca"), No("Detrito"),
    )),
    No("Integração/Comp", "tag-camera", PETROLEO, (
        No("Green screen"), No("Matte"), No("Passes/AOV"), No("Motion tracking"),
    )),
    No("Estilo", "tag-espelho", ROXO, (
        No("Realista"), No("Estilizado"), No("Cartoon FX"),
    )),
    No("Referência", "tag-papel", AREIA, (
        No("Reference footage"), No("Breakdown"),
    )),
)


class Template(NamedTuple):
    rotulo: str
    raizes: tuple[No, ...]


# Chave usada no seletor do diálogo e como argumento de `arvore`/`aplicar`/
# `previa` — a ordem aqui é a ordem que aparece na lista do diálogo.
TEMPLATES: dict[str, Template] = {
    "arquitetura": Template("Arquitetura", ARQUITETURA),
    "propaganda": Template("Propaganda/Publicidade", PROPAGANDA),
    "construcao": Template("Construção", CONSTRUCAO),
    "filme_animacao": Template("Filme & Animação", FILME_ANIMACAO),
    "gamedev": Template("Game Dev", GAMEDEV),
    "design_produto": Template("Design de Produto", DESIGN_PRODUTO),
    "vfx_simulacao": Template("VFX & Simulação", VFX_SIMULACAO),
}


def arvore(template: str, nivel: str) -> tuple[No, ...]:
    """O tronco do `template` podado na profundidade do `nivel`."""
    tpl = TEMPLATES.get(template)
    if tpl is None:
        raise ValueError(f"Template de tags desconhecido: {template!r}")
    profundidade = dict((k, p) for k, _, p in NIVEIS).get(nivel)
    if profundidade is None:
        raise ValueError(f"Nível de template desconhecido: {nivel!r}")
    return _podar(tpl.raizes, profundidade)


def _podar(nos: tuple[No, ...], restante: int) -> tuple[No, ...]:
    if restante <= 0:
        return ()
    return tuple(n._replace(filhos=_podar(n.filhos, restante - 1)) for n in nos)


def contar(nos: tuple[No, ...]) -> int:
    return sum(1 + contar(n.filhos) for n in nos)


class Resultado(NamedTuple):
    criadas: int
    existentes: int


def aplicar(conn: sqlite3.Connection, template: str, nivel: str) -> Resultado:
    """Cria o que falta e reaproveita o que já existe.

    Nunca sobrescreve: uma tag com o mesmo nome no mesmo pai mantém a cor,
    o ícone e os assets que o Rafael já tinha posto nela.
    """
    criadas = existentes = 0
    fila: list[tuple[No, int | None, str | None]] = [
        (n, None, None) for n in arvore(template, nivel)
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

    log.info("Template de tags %r/%r aplicado: %d criadas, %d já existiam.",
             template, nivel, criadas, existentes)
    return Resultado(criadas, existentes)


def previa(conn: sqlite3.Connection, template: str,
          nivel: str) -> list[tuple[No, int, str | None, bool]]:
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

    caminhar(arvore(template, nivel), 0, None, None)
    return saida


def _id_de(conn: sqlite3.Connection, nome: str, pai_id: int | None) -> int | None:
    row = conn.execute(
        "SELECT id FROM tags WHERE name = ? AND parent_id IS ? AND deleted_at IS NULL",
        (nome, pai_id),
    ).fetchone()
    return row["id"] if row else None


def _existe(conn: sqlite3.Connection, nome: str, pai_id: int | None) -> bool:
    return _id_de(conn, nome, pai_id) is not None
