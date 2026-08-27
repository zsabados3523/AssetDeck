"""Detecta texturas que são DEPENDÊNCIAS de um modelo/material irmão.

O fluxo do Rafael: cada material (Poliigon, PolyHaven…) é convertido num
.blend que fica ao lado dos mapas; modelos trazem suas texturas numa
subpasta. Nos dois casos ele quer ver o .blend — não os mapas soltos.

Regra: uma textura é dependência se existe um arquivo de modelo (.blend,
.fbx, .obj…) na mesma pasta ou em até DOIS níveis acima. Dois níveis cobrem
'Material/4K/mapa.jpg' e 'Modelo/textures/mapa.png' sem varrer a biblioteca
inteira para cima.

Também associa o preview que vem nos packs ('*_Preview1.png') como capa do
modelo irmão — o Poliigon já entrega essa imagem pronta.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Tipos que PODEM ser dependência (um modelo nunca é dependência de outro)
DEPENDENT_TYPES = ("texture", "pbr_set", "cutout")
# Tipos cuja presença numa pasta torna as texturas vizinhas dependências
OWNER_TYPES = ("model", "scene")

MAX_LEVELS_UP = 2

_PREVIEW_RE = re.compile(r"_preview\d*$", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir_of(rel_path: str) -> str:
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def _pacote_de(rel_path: str) -> str:
    """A pasta que CONTÉM a pasta do arquivo — o "pacote" a que ele pertence.

    Existe por causa de como os packs comerciais se organizam (Fatia 81,
    relatado pelo Rafael: "assinalar previews por nome não parece estar
    funcionando"). Um Maxtree separa modelo e prévia em pastas IRMÃS:

        Maxtree Vol 148/MT_PM_V148_Blender_CyclesEevee/MT_..._01_01.blend
        Maxtree Vol 148/MT_PM_V148_Thumbnails/        MT_..._01_01.jpg

    Nome idêntico, pasta diferente. Casar só dentro da MESMA pasta — como
    a Fatia 57 fazia — descartava todos: medido na biblioteca real dele,
    0 de 2.530 modelos sem capa casavam; subindo um nível, 342. Na testlib,
    de 8 para 69.

    Um nível só, de propósito: o pacote é a fronteira natural desse tipo de
    coleção. Subir mais deixaria um modelo casar com a imagem de outro
    canto qualquer da biblioteca.

    E quando esse nível acima é a RAIZ da biblioteca, o escopo volta a ser
    a própria pasta do arquivo. Sem essa ressalva, 'MOVEIS/Banco.blend' e
    'OUTRAPASTA/Banco.jpg' passariam a casar — as duas pastas são "irmãs"
    na raiz, mas raiz não é pacote, é a biblioteca inteira. Foi um teste
    da Fatia 57 (`test_pasta_diferente_nao_casa_por_engano`) que pegou esse
    exagero quando a regra foi afrouxada.
    """
    pasta = _dir_of(rel_path)
    acima = _dir_of(pasta)
    return acima or pasta


# Sufixo numérico de sequência no fim do nome: "_01", "-02", "_v003", e
# "_preview1"/"_Preview1" (achado real: "ChairMakilReplica001_preview1.png"
# ao lado de "ChairMakilReplica001.blend" — 264 arquivos assim na
# biblioteca, batendo 0 antes desta correção porque "preview1" não é só
# um "v" opcional seguido de dígito).
# Usado SÓ no nome da imagem, nunca no do modelo — muitos modelos terminam
# em número de catálogo ("Chair_125_029.blend") e normalizá-los quebraria
# tudo (viraria "Chair", casando com qualquer cadeira).
_SUFIXO_SEQUENCIA = re.compile(r"[-_](?:preview_?)?v?\d+$", re.IGNORECASE)

# Pasta de prévias que os packs criam ao lado do modelo (Chaos Cosmos).
_PASTA_PREVIEWS = "previews"

# Marcador de conversão colado no NOME DO MODELO — achado real: Poliigon
# entrega 'ArmchairAbbraccioReplica001_preview1.png', mas o .blend
# convertido virou 'ArmchairAbbraccioReplica001_Blender_Cycles.blend'
# (137 casos) ou '..._Cycles.blend' (132 casos). Diferente do sufixo de
# sequência: aqui é seguro normalizar o nome do MODELO, porque a lista é
# fechada (palavras específicas do conversor, não um número qualquer que
# poderia ser catálogo de verdade). Casos tipo 'Chair_Cycles.blend' e
# 'Stool_Cycles.blend' na MESMA pasta (2 achados) continuam ambíguos de
# propósito — o "Chair"/"Stool" no meio não é marcador de conversão, é
# parte do nome, e a proteção de "único nos dois sentidos" da Fatia 81
# já lida com isso sem precisar de regra nova.
_SUFIXO_CONVERSAO = re.compile(r"_(?:blender_)?cycles$", re.IGNORECASE)


def _bases_do_modelo(stem: str) -> list[str]:
    """Nomes que este MODELO pode ser encontrado por — o stem original,
    mais o stem sem o marcador de conversão, se houver um."""
    sem_conversao = _SUFIXO_CONVERSAO.sub("", stem)
    if sem_conversao != stem and sem_conversao:
        return [stem, sem_conversao]
    return [stem]


def _bases_da_imagem(stem: str) -> list[str]:
    """Nomes de modelo que esta imagem PODE estar servindo.

    O Chaos Cosmos entrega 'Chair_125_029.blend' com
    'previews/Chair_125_029_01.png' e '_02.png' — mesmo nome mais um sufixo
    de sequência. Devolve o stem inteiro e ele sem 1 e sem 2 sufixos, porque
    aparecem os dois formatos na biblioteca do Rafael ('_01' e '_01_v001').
    Tirar mais que dois começaria a comer o número de catálogo do próprio
    modelo.
    """
    saida = [stem]
    atual = stem
    for _ in range(2):
        novo = _SUFIXO_SEQUENCIA.sub("", atual)
        if novo == atual or not novo:
            break
        atual = novo
        saida.append(atual)
    return saida


def _escopos_de(rel_path: str) -> set[str]:
    """Onde este arquivo "conta" pra efeito de casamento.

    A pasta dele e a de cima. Duas pastas casam quando os conjuntos se
    cruzam, o que cobre os três arranjos reais das bibliotecas dele:
    imagem na MESMA pasta do modelo; imagem numa SUBPASTA dele
    ('previews/', Cosmos); e imagem numa pasta IRMÃ ('Thumbnails/',
    Maxtree). A raiz ("") fica de fora de propósito — senão duas pastas
    quaisquer no topo da biblioteca passariam a se enxergar.
    """
    pasta = _dir_of(rel_path)
    acima = _dir_of(pasta)
    return {pasta} | ({acima} if acima else set())


def _ancestors(directory: str, levels: int) -> list[str]:
    """['a/b/c', 'a/b', 'a'] limitado a `levels` subidas."""
    saida = [directory]
    atual = directory
    for _ in range(levels):
        if not atual:
            break
        atual = atual.rsplit("/", 1)[0] if "/" in atual else ""
        saida.append(atual)
    return saida


def detect(conn: sqlite3.Connection, library_id: int) -> int:
    """Recalcula is_dependency para a biblioteca. Retorna quantas mudaram.

    Uma pasta "tem modelo" se existe um .blend/.fbx nela OU em qualquer
    subpasta — packs como o Maxtree separam os .blend e os mapas em pastas
    IRMÃS (Vol_148/Blender_CyclesEevee/ e Vol_148/Maps/), e as texturas
    continuam sendo dependências daqueles modelos.
    """
    pastas_com_modelo: set[str] = set()
    for row in conn.execute(
        f"""SELECT DISTINCT f.rel_path FROM files f JOIN assets a ON a.id = f.asset_id
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})""",
        (library_id, *OWNER_TYPES),
    ):
        # A pasta do modelo e TODAS as suas ancestrais passam a "ter modelo"
        atual = _dir_of(row["rel_path"])
        while atual:
            pastas_com_modelo.add(atual)
            atual = atual.rsplit("/", 1)[0] if "/" in atual else ""
    # A raiz da biblioteca nunca conta: senão a biblioteca inteira viraria
    # dependência do primeiro modelo encontrado.
    pastas_com_modelo.discard("")

    candidatos = conn.execute(
        f"""SELECT a.id, a.is_dependency, f.rel_path
            FROM assets a JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(DEPENDENT_TYPES))})""",
        (library_id, *DEPENDENT_TYPES),
    ).fetchall()

    mudou = 0
    for row in candidatos:
        pasta = _dir_of(row["rel_path"])
        dependente = any(
            anc and anc in pastas_com_modelo
            for anc in _ancestors(pasta, MAX_LEVELS_UP)
        )
        novo = 1 if dependente else 0
        if novo != row["is_dependency"]:
            conn.execute(
                "UPDATE assets SET is_dependency = ?, updated_at = ? WHERE id = ?",
                (novo, _now(), row["id"]),
            )
            mudou += 1

    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE library_id = ? AND is_dependency = 1"
        " AND deleted_at IS NULL", (library_id,),
    ).fetchone()["n"]
    log.info("Dependências: %d assets marcados (%d mudaram nesta passada).",
             total, mudou)
    return mudou


def attach_pack_previews(conn: sqlite3.Connection, library_id: int,
                         library_root, previews_dir) -> int:
    """Usa os '*_Preview1.png' dos packs como capa do modelo irmão.

    Poliigon e outros já entregam essa imagem pronta — melhor do que
    renderizar. Retorna quantas capas foram criadas.
    """
    from pathlib import Path

    from assetdeck.db.repos import previews as previews_repo

    # Modelos sem capa, indexados por pasta
    modelos: dict[str, tuple[int, str]] = {}
    for row in conn.execute(
        f"""SELECT a.id, f.rel_path FROM assets a
            JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})
              AND NOT EXISTS (SELECT 1 FROM previews p
                              WHERE p.asset_id = a.id AND p.is_cover = 1
                                AND p.deleted_at IS NULL)""",
        (library_id, *OWNER_TYPES),
    ):
        modelos[_dir_of(row["rel_path"])] = (row["id"], row["rel_path"])

    if not modelos:
        return 0

    criadas = 0
    for row in conn.execute(
        """SELECT f.rel_path FROM files f JOIN assets a ON a.id = f.asset_id
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
        (library_id,),
    ):
        rel = row["rel_path"]
        nome = rel.rsplit("/", 1)[-1]
        base, _, ext = nome.rpartition(".")
        if ext.lower() not in ("png", "jpg", "jpeg") or not _PREVIEW_RE.search(base):
            continue
        alvo = modelos.get(_dir_of(rel))
        if alvo is None:
            continue
        asset_id, _p = alvo
        try:
            previews_repo.add(conn, asset_id, Path(library_root) / rel,
                              Path(previews_dir), origin="auto")
            criadas += 1
            del modelos[_dir_of(rel)]  # um preview por modelo basta
        except (OSError, FileNotFoundError):
            log.warning("Preview do pack ilegível: %s", rel, exc_info=True)

    if criadas:
        log.info("Capas automáticas de packs: %d modelos ganharam preview.", criadas)
    return criadas


def attach_stem_match_previews(conn: sqlite3.Connection, library_id: int,
                               library_root, previews_dir,
                               hide_source: bool = False) -> int:
    """Casa 'Cadeira.blend' com 'Cadeira.jpg' pelo NOME e usa a imagem como
    capa automática do modelo (Fatia 57, pedido do Rafael).

    **Fatia 81:** o casamento deixou de exigir a MESMA pasta e passou a
    aceitar pasta IRMÃ (mesmo pacote — ver `_pacote_de`). O Rafael relatou
    que a função "não parecia estar funcionando": ela funcionava, mas a
    regra de mesma pasta não alcançava a organização real da biblioteca
    dele, onde os packs separam modelo e prévia em pastas irmãs. Medido:
    0 de 2.530 modelos sem capa casavam na biblioteca real; agora 342. Na
    testlib, de 8 para 69.

    Diferente de `attach_pack_previews` (que casa por PASTA, um preview por
    pasta): aqui um pacote pode ter vários modelos, cada um casando com a
    própria imagem de mesmo nome. Só aplica quando o par é ÚNICO nos dois
    sentidos — uma imagem para aquele nome e um modelo para aquele nome.
    Qualquer disputa é pulada e logada, nunca adivinhada (regra do projeto:
    nenhum erro silencioso).

    `hide_source=True` some a imagem da grade (reversível, mesmo flag
    `hidden` do drag-and-drop manual) — separado do `hide_preview_source`
    do fluxo manual porque este roda em lote, sem ninguém pra responder um
    diálogo "ocultar origem?" no meio da varredura.

    Retorna quantas capas foram criadas.
    """
    from pathlib import Path

    from assetdeck.db.repos import assets as assets_repo
    from assetdeck.db.repos import previews as previews_repo
    from assetdeck.thumbs.preview import can_preview

    # Modelos sem capa. Indexados por NOME (minúsculo), guardando lista: dois
    # modelos de mesmo nome disputando a mesma imagem é ambíguo e tem de ser
    # pulado. Antes da Fatia 81 isto era um par único e o segundo modelo
    # sobrescrevia o primeiro em silêncio.
    modelos: dict[str, list[tuple[int, str]]] = {}
    for row in conn.execute(
        f"""SELECT a.id, f.rel_path FROM assets a
            JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
            WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL
              AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})
              AND NOT EXISTS (SELECT 1 FROM previews p
                              WHERE p.asset_id = a.id AND p.is_cover = 1
                                AND p.deleted_at IS NULL)""",
        (library_id, *OWNER_TYPES),
    ):
        rel = row["rel_path"]
        # Registrado sob o nome cru E sob o nome sem marcador de conversão
        # (se houver): a imagem pode bater com qualquer um dos dois.
        for chave in _bases_do_modelo(Path(rel).stem.lower()):
            modelos.setdefault(chave, []).append((row["id"], rel))

    if not modelos:
        return 0

    # Quantos modelos existem em cada pasta — a regra de PASTA (abaixo) só
    # vale onde há exatamente UM, senão não dá pra saber de quem é a prévia.
    # `set()` primeiro: um modelo com marcador de conversão aparece em DUAS
    # entradas de `modelos` (nome cru + normalizado) — sem isso, contaria
    # a mesma pasta 2x e uma pasta de 1 modelo só pareceria ter 2.
    ids_por_pasta: dict[str, set[int]] = {}
    for lista in modelos.values():
        for aid, rel in lista:
            ids_por_pasta.setdefault(_dir_of(rel), set()).add(aid)
    modelos_por_pasta = {pasta: len(ids) for pasta, ids in ids_por_pasta.items()}

    # Candidatas por modelo: chave = nome do modelo, valor = lista de
    # (rel_path, asset_id). Duas formas de virar candidata:
    #
    #  1. POR NOME — o stem da imagem, tirando o sufixo de sequência, bate
    #     com o nome do modelo, e os escopos se cruzam (mesma pasta,
    #     subpasta ou pasta irmã). Cobre Maxtree e a maioria do Cosmos.
    #  2. POR PASTA — a imagem está numa subpasta "previews/" do modelo.
    #     ~11% das prévias do Cosmos têm nome de hash
    #     ("a586041c_1755512249817171783.png"), sem relação nenhuma com o
    #     nome do modelo; só a pasta as liga. Exige um único modelo na pasta.
    candidatos: dict[str, list[tuple[str, int]]] = {}
    for row in conn.execute(
        """SELECT f.rel_path, a.id AS asset_id FROM files f
           JOIN assets a ON a.id = f.asset_id
           WHERE a.library_id = ? AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
        (library_id,),
    ):
        rel = row["rel_path"]
        p = Path(rel)
        if not can_preview(p):
            continue

        pasta = _dir_of(rel)
        acima = _dir_of(pasta)
        escopos = _escopos_de(rel)

        # (1) por nome
        casou = False
        for base in _bases_da_imagem(p.stem):
            chave = base.lower()
            donos = modelos.get(chave)
            if not donos:
                continue
            if any(escopos & _escopos_de(m_rel) for _aid, m_rel in donos):
                candidatos.setdefault(chave, []).append((rel, row["asset_id"]))
                casou = True
                break
        if casou:
            continue

        # (2) por pasta: .../<pasta do modelo>/previews/<qualquer imagem>
        if pasta.rsplit("/", 1)[-1].lower() != _PASTA_PREVIEWS:
            continue
        if modelos_por_pasta.get(acima, 0) != 1:
            continue
        for chave, donos in modelos.items():
            if any(_dir_of(m_rel) == acima for _aid, m_rel in donos):
                candidatos.setdefault(chave, []).append((rel, row["asset_id"]))
                break

    criadas = 0
    for chave, itens in candidatos.items():
        donos = modelos[chave]
        if len(donos) != 1:
            # Dois modelos de mesmo nome: não dá pra saber de quem é a imagem.
            log.info("Preview por nome ambíguo em %r: %d modelos disputam a "
                     "mesma imagem — pulado (%s).", chave, len(donos),
                     ", ".join(rel for _aid, rel in donos))
            continue

        # Dois arquivos com o MESMO nome-base (Mesa.jpg e Mesa.png) são um
        # empate de verdade: as duas dizem ser "a" imagem do modelo, e
        # escolher seria adivinhar. Já nomes DIFERENTES ("_01", "_02") são
        # uma sequência — o pack entregou vários ângulos, e o primeiro é a
        # capa natural.
        por_nome: dict[str, list[tuple[str, int]]] = {}
        for rel, aid in itens:
            por_nome.setdefault(Path(rel).stem.lower(), []).append((rel, aid))
        empatados = [k for k, v in por_nome.items() if len(v) > 1]
        if empatados:
            log.info("Preview ambíguo em %r: nome-base repetido em %s — "
                     "pulado.", chave, ", ".join(sorted(empatados)))
            continue

        # Ordem natural pelo nome: "_01" antes de "_02"; o primeiro é a capa.
        em_ordem = sorted(itens, key=lambda par: Path(par[0]).name.lower())
        rel_imagem, imagem_asset_id = em_ordem[0]
        asset_id, _modelo_rel = donos[0]
        try:
            previews_repo.add(conn, asset_id, Path(library_root) / rel_imagem,
                              Path(previews_dir), origin="auto")
            criadas += 1
            if hide_source:
                assets_repo.set_hidden(conn, imagem_asset_id, True)
        except (OSError, FileNotFoundError):
            log.warning("Preview por nome ilegível: %s", rel_imagem, exc_info=True)

    if criadas:
        log.info("Capas automáticas por nome: %d modelos ganharam preview.", criadas)
    return criadas
