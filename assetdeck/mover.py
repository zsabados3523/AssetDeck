"""Mover assets de pasta DENTRO da biblioteca (Fatia 85).

Pedido do Rafael: "eu percebi que tem uma árvore na pasta de vasos, porém
até eu mover no navegador de arquivos iria demorar demais… será que não
teria a possibilidade de eu selecionar os assets no grid e arrastar para a
pasta que quero?".

**Este módulo ESCREVE na biblioteca.** O `CLAUDE.md` dizia "o app é
somente-leitura sobre a biblioteca; nada move, renomeia ou apaga" — a
regra foi aberta por ele nesta fatia, e a linha lá foi atualizada. O
`batch_rename` já era uma exceção (renomeia no disco desde a Fatia 23);
esta é a segunda, e as duas seguem o mesmo padrão: item problemático é
pulado e logado, nunca derruba o lote.

**O que se move é a PASTA do asset, não o arquivo.** Um `.blend` quase
nunca é um arquivo solto: no Chaos Cosmos ele tem `textures_cache/` e
`previews/` embaixo; mover só o `.blend` entrega um asset quebrado no
destino. Por isso um asset só é movível quando é DONO da própria pasta —
quando nenhum OUTRO modelo/cena mora nela. Textura, imagem e preview que
estejam ali dentro viajam junto, porque a pasta é o asset.

Quem divide pasta (um Maxtree, com 108 arquivos e dezenas de modelos na
mesma pasta) é RECUSADO, com motivo. O Rafael aceitou explicitamente esse
limite: "eu já aceitei que os do maxtree por exemplo ficarão na mesma
pasta onde estão".
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from assetdeck.indexer.dependencies import OWNER_TYPES

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Movimento:
    """Um asset que PODE ser movido, e o que vai junto com ele."""

    asset_id: int
    nome: str
    origem: str          # pasta atual, relativa à raiz
    destino: str         # pasta nova, relativa à raiz
    arquivos: int        # quantos arquivos indexados moram na pasta
    bytes: int


@dataclass(frozen=True)
class Recusa:
    """Um asset que NÃO pode ser movido, e por quê — em português, porque
    esta frase vai direto pra tela do Rafael."""

    asset_id: int
    nome: str
    motivo: str


@dataclass(frozen=True)
class Plano:
    mover: list[Movimento]
    recusar: list[Recusa]

    @property
    def total_arquivos(self) -> int:
        return sum(m.arquivos for m in self.mover)

    @property
    def total_bytes(self) -> int:
        return sum(m.bytes for m in self.mover)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir_of(rel_path: str) -> str:
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def planejar(conn: sqlite3.Connection, library_id: int, library_root: Path,
             asset_ids: list[int], destino: str) -> Plano:
    """Decide o que dá pra mover, sem tocar em disco nenhum.

    `destino` é uma pasta relativa à raiz da biblioteca ("" = a própria
    raiz). Devolve o que move e o que é recusado, com motivo — a UI mostra
    isso ao Rafael ANTES de qualquer arquivo sair do lugar.
    """
    raiz = Path(library_root)
    mover: list[Movimento] = []
    recusar: list[Recusa] = []

    for asset_id in asset_ids:
        linha = conn.execute(
            """SELECT a.id, a.name, a.is_dependency, f.rel_path
               FROM assets a JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
               WHERE a.id = ? AND a.library_id = ?
                 AND a.deleted_at IS NULL AND f.deleted_at IS NULL""",
            (asset_id, library_id),
        ).fetchone()
        if linha is None:
            recusar.append(Recusa(asset_id, f"#{asset_id}",
                                  "não está mais na biblioteca"))
            continue

        nome = linha["name"]
        pasta = _dir_of(linha["rel_path"])
        if not pasta:
            recusar.append(Recusa(asset_id, nome,
                                  "está solto na raiz da biblioteca, sem pasta própria"))
            continue

        # Quem mais mora nesta pasta (e abaixo dela)? O que bloqueia é
        # outro MODELO/CENA — dois assets de verdade dividindo pasta, como
        # os Maxtree. Textura, imagem e preview que estejam ali dentro
        # viajam junto: a pasta É o asset (no Cosmos, `textures_cache/` e
        # `previews/` só fazem sentido ao lado do `.blend`).
        #
        # Deliberadamente NÃO se usa `is_dependency` aqui: essa marca é
        # calculada por `dependencies.detect()`, que roda na varredura. Numa
        # biblioteca recém-indexada ela ainda pode estar zerada, e o mover
        # recusaria assets legítimos sem explicação que o Rafael pudesse
        # entender.
        vizinhos = conn.execute(
            f"""SELECT DISTINCT a.id, a.name
                FROM assets a JOIN files f ON f.asset_id = a.id
                WHERE a.library_id = ? AND a.deleted_at IS NULL
                  AND f.deleted_at IS NULL
                  AND a.asset_type IN ({','.join('?' * len(OWNER_TYPES))})
                  AND (f.rel_path = ? OR f.rel_path LIKE ?)""",
            (library_id, *OWNER_TYPES, pasta, pasta + "/%"),
        ).fetchall()
        estranhos = [v for v in vizinhos if v["id"] != asset_id]
        if estranhos:
            exemplos = ", ".join(v["name"] for v in estranhos[:3])
            recusar.append(Recusa(
                asset_id, nome,
                f"divide a pasta com outros {len(estranhos)} assets "
                f"({exemplos}…) — mover levaria todos juntos",
            ))
            continue

        if _dir_of(pasta) == destino or pasta == destino:
            recusar.append(Recusa(asset_id, nome, "já está nessa pasta"))
            continue

        alvo = f"{destino}/{Path(pasta).name}" if destino else Path(pasta).name
        if (raiz / alvo).exists():
            recusar.append(Recusa(
                asset_id, nome,
                f"já existe uma pasta chamada {Path(pasta).name!r} no destino",
            ))
            continue

        arquivos = conn.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(f.size_bytes), 0) AS b
               FROM files f JOIN assets a ON a.id = f.asset_id
               WHERE a.library_id = ? AND f.deleted_at IS NULL
                 AND (f.rel_path = ? OR f.rel_path LIKE ?)""",
            (library_id, pasta, pasta + "/%"),
        ).fetchone()
        mover.append(Movimento(asset_id, nome, pasta, alvo,
                               arquivos["n"], arquivos["b"]))

    return Plano(mover=mover, recusar=recusar)


def executar(conn: sqlite3.Connection, library_id: int, library_root: Path,
             plano: Plano) -> tuple[int, int]:
    """Move as pastas no disco e reaponta os `rel_path` no banco.

    Devolve (movidos, falhas). Uma falha NÃO derruba o resto — mesmo
    padrão do `batch_rename`: o item problemático é logado com contexto e
    o lote continua.

    A ordem importa: primeiro o disco, depois o banco. Se o `shutil.move`
    falhar, o banco fica intocado e a biblioteca segue coerente; o
    contrário deixaria o banco apontando pra um lugar onde não há nada.
    """
    raiz = Path(library_root)
    movidos = falhas = 0

    for m in plano.mover:
        origem_abs = raiz / m.origem
        destino_abs = raiz / m.destino
        try:
            if not origem_abs.is_dir():
                raise FileNotFoundError(f"pasta sumiu antes do move: {origem_abs}")
            if destino_abs.exists():
                raise FileExistsError(f"já existe algo em {destino_abs}")
            destino_abs.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(origem_abs), str(destino_abs))
        except OSError:
            log.exception("Mover falhou: %s -> %s — pulando.",
                          origem_abs, destino_abs)
            falhas += 1
            continue

        # Reaponta TODOS os arquivos que moravam na pasta — o asset, as
        # dependências dele e os sidecars, que viajaram junto por estarem
        # dentro da pasta movida.
        agora = _now()
        for linha in conn.execute(
            """SELECT f.id, f.rel_path FROM files f
               JOIN assets a ON a.id = f.asset_id
               WHERE a.library_id = ? AND f.deleted_at IS NULL
                 AND (f.rel_path = ? OR f.rel_path LIKE ?)""",
            (library_id, m.origem, m.origem + "/%"),
        ).fetchall():
            novo = m.destino + linha["rel_path"][len(m.origem):]
            conn.execute(
                "UPDATE files SET rel_path = ?, updated_at = ? WHERE id = ?",
                (novo, agora, linha["id"]),
            )
        conn.commit()
        movidos += 1
        log.info("Asset %r movido: %s -> %s (%d arquivos).",
                 m.nome, m.origem, m.destino, m.arquivos)

    if falhas:
        log.warning("Mover assets: %d movidos, %d falharam (ver acima).",
                    movidos, falhas)
    return movidos, falhas
