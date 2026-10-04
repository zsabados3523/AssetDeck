"""Varredura da biblioteca: descobre arquivos e grava assets/files no banco.

Regras desta fatia:
- 1 arquivo = 1 asset (o agrupamento PBR é a Fatia 6).
- A biblioteca é SOMENTE-LEITURA: aqui só se lê o disco e se escreve no banco.
- Idempotente: rodar de novo não duplica nada. Arquivo inalterado (mesmo
  tamanho + mtime) é pulado; alterado é atualizado; sumido ganha
  missing_since (nunca é apagado); reaparecido tem o missing_since limpo.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
import uuid as uuid_mod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Callable

from assetdeck.sidecar.reader import read_sidecar, restorable_fields
from assetdeck.sidecar.writer import sidecar_path

log = logging.getLogger(__name__)


def _uuid_livre(conn: sqlite3.Connection, uuid: str) -> bool:
    return conn.execute("SELECT 1 FROM assets WHERE uuid = ?", (uuid,)).fetchone() is None


def image_meta(
    path: Path,
) -> tuple[int | None, int | None, int | None, int | None, str | None, str | None]:
    """(width, height, has_alpha, bit_depth, phash, dominant_color) numa
    única abertura do arquivo (phash e cor média são baratos — só reamostram
    a imagem — não vale abrir de novo pra cada um).
    Formatos não-raster ou ilegíveis devolvem tudo None, sem erro."""
    from assetdeck.thumbs.raster import RASTER_EXTS

    if path.suffix.lower().lstrip(".") not in RASTER_EXTS:
        return None, None, None, None, None, None
    try:
        from assetdeck.thumbs.dominant_color import dominant_color_from_image
        from assetdeck.thumbs.phash import phash_from_image
        from assetdeck.thumbs.raster import open_image

        with open_image(path) as img:
            has_alpha = 1 if "A" in img.getbands() else 0
            bit_depth = 16 if img.mode.startswith("I;16") else 8
            phash = phash_from_image(img)
            dominant_color = dominant_color_from_image(img)
            return img.width, img.height, has_alpha, bit_depth, phash, dominant_color
    except Exception:
        log.warning("Não consegui ler o cabeçalho de imagem de %s", path, exc_info=True)
        return None, None, None, None, None, None

# Extensão (minúscula, sem ponto) → asset_type do schema.
# O que não está aqui é ignorado (contado e logado, nunca erro).
EXT_MAP = {
    # imagens comuns — tipo refinado depois (cutout na Fatia 7, PBR na 6)
    "jpg": "texture", "jpeg": "texture", "png": "texture", "tif": "texture",
    "tiff": "texture", "webp": "texture", "bmp": "texture", "tga": "texture",
    "gif": "texture",
    # alto alcance dinâmico
    "hdr": "hdri", "exr": "hdri",
    # referências
    "pdf": "reference",
    # modelos 3D
    "blend": "model", "fbx": "model", "obj": "model", "gltf": "model",
    "glb": "model", "dae": "model", "stl": "model",
    # outros programas (Fatia 37): só reconhecer e catalogar — sem
    # preview real, sem SDK do fabricante. Entram como 'model' de
    # propósito: categoria, dependências e chip de extensão já
    # funcionam automático, sem valor novo no enum (evita migration).
    "rvt": "model",   # Revit
    "skp": "model",   # SketchUp
    "usd": "model", "usda": "model", "usdc": "model", "usdz": "model",
    "abc": "model",   # Alembic
    # vetores (dwg incluído a pedido do Rafael — desenhos CAD)
    "svg": "vector", "ai": "vector", "eps": "vector", "cdr": "vector",
    "dwg": "vector",
    # fotometria e color grading
    "ies": "ies", "cube": "lut", "3dl": "lut",
    # photoshop
    "psd": "psd", "psb": "psd",
    # materiais MaterialX
    "mtlx": "other",
}

_FINGERPRINT_CHUNK = 1024 * 1024  # 1MB de cada ponta


@dataclass
class ScanStats:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
    reappeared: int = 0
    restored: int = 0      # metadados recuperados de sidecars .json
    grouped_sets: int = 0  # sets PBR criados pelo agrupador (pós-varredura)
    ignored: int = 0
    errors: int = 0
    aborted: bool = False
    ignored_exts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [f"{self.added} novos", f"{self.unchanged} inalterados"]
        if self.restored:
            parts.append(f"{self.restored} restaurados de sidecar")
        if self.grouped_sets:
            parts.append(f"{self.grouped_sets} sets PBR agrupados")
        if self.updated:
            parts.append(f"{self.updated} atualizados")
        if self.missing:
            parts.append(f"{self.missing} sumidos")
        if self.reappeared:
            parts.append(f"{self.reappeared} reapareceram")
        if self.ignored:
            parts.append(f"{self.ignored} ignorados")
        if self.errors:
            parts.append(f"{self.errors} erros (ver log)")
        if self.aborted:
            parts.append("interrompida")
        return ", ".join(parts)


def classify(path: Path) -> str | None:
    """asset_type pela extensão, ou None se o arquivo não nos interessa."""
    return EXT_MAP.get(path.suffix.lower().lstrip("."))


def fingerprint(path: Path) -> str:
    """Impressão digital rápida: blake2b de tamanho + primeiro/último 1MB.

    Suficiente para relocalização e barata mesmo em .blend de gigabytes.
    O algoritmo fica registrado em files.hash_algo ('blake2b-fp1m').
    """
    size = path.stat().st_size
    h = hashlib.blake2b(digest_size=20)
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(_FINGERPRINT_CHUNK))
        if size > 2 * _FINGERPRINT_CHUNK:
            f.seek(-_FINGERPRINT_CHUNK, os.SEEK_END)
            h.update(f.read(_FINGERPRINT_CHUNK))
    return h.hexdigest()


# Quantos processos a varredura usa pra calcular hash e metadados de
# imagem. QUATRO por medição, não por chute: na máquina do Rafael (16
# núcleos, biblioteca num SSD externo) 4 processos deram 40 arq/s contra
# 11 em série — e 8 deram 28, PIOR que 4, porque a partir dali o disco vira
# o gargalo e os processos passam a disputar I/O em vez de somar CPU.
WORKERS_PADRAO = 4

# Tamanho do bloco processado por vez. Existe pra que "Parar" e a barra de
# progresso continuem respondendo: com um único `map` sobre a biblioteca
# inteira, cancelar no meio não teria efeito nenhum até o fim.
_BLOCO = 100

# `stat()` em caminhos SMB/GVFS espera resposta da rede e quase não consome
# CPU. Sobrepor algumas consultas reduz o tempo ocioso sem abrir conteúdo em
# paralelo nem multiplicar a carga de leitura do NAS.
_STAT_WORKERS = 4


def calcular_pesado(path: Path) -> tuple:
    """A parte cara de um arquivo: impressão digital + metadados de imagem.

    Módulo de nível de topo e sem estado de propósito — é isto que roda nos
    processos filhos, e só função importável é picklável.

    NÃO muda nenhuma conta: são exatamente `fingerprint` e `image_meta`, os
    mesmos de sempre. Isso importa porque o phash é comparado por
    IGUALDADE EXATA na detecção de duplicados — qualquer mudança no cálculo
    faria arquivos indexados antes e depois pararem de casar entre si.
    """
    return fingerprint(path), image_meta(path)


def _preparar_worker() -> None:
    """Roda UMA vez em cada processo filho, antes da primeira tarefa.

    **Por que existe** (Rafael, 2026-08-19: "meu PC fica com 100% de uso de
    CPU e está começando a dar erros"): o OpenCV abre, POR PROCESSO, uma
    thread por núcleo — 16 nesta máquina. Com 4 processos de varredura são
    até 64 threads disputando 16 núcleos. O trabalho não anda mais rápido
    (o paralelismo útil já está no nível de PROCESSO, medido em 4), só
    afoga o resto do computador.

    Uma thread por processo, e um `nice` que põe a varredura atrás de tudo
    que o Rafael estiver fazendo: ela roda em segundo plano, não tem
    pressa, e não pode deixar a máquina inutilizável enquanto roda.
    """
    try:
        import cv2

        cv2.setNumThreads(1)
    except Exception:
        log.warning("Não consegui limitar as threads do OpenCV no worker.",
                    exc_info=True)
    try:
        os.nice(10)
    except OSError:
        log.warning("Não consegui baixar a prioridade do worker.", exc_info=True)


# Bibliotecas numéricas leem estas variáveis NA HORA DO IMPORT — por isso
# são postas no ambiente do PAI antes de subir o pool (`spawn` copia o
# ambiente pro filho), e não dentro de `_preparar_worker`, que roda tarde
# demais pra elas. No pai não mudam nada: numpy/cv2 já foram importados.
_AMBIENTE_1_THREAD = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def _abrir_pool(workers: int):
    """Pool de processos pra varredura, ou `None` pra ir em série.

    **`spawn`, não `fork`** — e isto não é preferência. A varredura roda
    numa thread do Qt (`ScanController`), e o próprio Python avisa que
    `fork()` num processo multi-thread pode travar o filho
    (DeprecationWarning no 3.12, padrão mudando nas próximas versões). Um
    deadlock aqui congelaria a indexação sem erro nenhum na tela — o pior
    tipo de falha. `spawn` custa uns 100ms a mais pra subir cada processo,
    pagos UMA vez por varredura.

    Devolve `None` se o pool não subir (limite de processos, app
    empacotado): a varredura tem de acontecer de qualquer jeito, só mais
    devagar.
    """
    if workers <= 1:
        return None
    try:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        os.environ.update(_AMBIENTE_1_THREAD)
        pool = ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_preparar_worker)
        log.info("Pool de fingerprints iniciado com %d processo(s).", workers)
        return pool
    except Exception:
        log.warning("Pool de processos indisponível — varrendo em série.",
                    exc_info=True)
        return None


def _pre_calcular(pool, paths: list[Path], should_stop=None) -> dict[Path, tuple]:
    """Calcula o bloco em paralelo (ou em série, se não houver pool).

    Consome o `map` PREGUIÇOSAMENTE e olha `should_stop` a cada resultado.
    Sem isso, fechar o app no meio de uma varredura esperava o bloco inteiro
    terminar — o `ScanController` reclamava "thread não terminou em 5000ms" e
    matava a thread na marra. Parar aqui ainda espera as tarefas JÁ em voo
    (no máximo alguns arquivos por processo), não as 200 do bloco.
    """
    if not paths:
        return {}
    if pool is None:
        saida = {}
        for p in paths:
            if should_stop and should_stop():
                break
            saida[p] = calcular_pesado(p)
        return saida
    try:
        saida = {}
        for path, resultado in zip(paths, pool.map(calcular_pesado, paths, chunksize=4)):
            saida[path] = resultado
            if should_stop and should_stop():
                log.info("Pré-cálculo interrompido a pedido (%d de %d do bloco).",
                         len(saida), len(paths))
                break
        return saida
    except Exception:
        # Um pool que morreu no meio não pode levar a varredura junto.
        log.warning("Pool falhou neste bloco — calculando em série.", exc_info=True)
        return {p: calcular_pesado(p) for p in paths}


def iter_library_files(root: Path, on_error: Callable[[OSError], None] | None = None):
    """Percorre em fluxo, sem montar/ordenar uma pasta inteira em memória.

    `os.walk` só entrega os arquivos de uma pasta depois de enumerá-los todos.
    Em pastas enormes sobre NAS isso pode atrasar o primeiro lote. `scandir`
    permite entregar cada arquivo conforme o servidor o retorna. Diretórios
    ocultos e links para diretórios continuam fora da árvore, como em `os.walk`
    com `followlinks=False`.
    """
    pendentes = [Path(root)]
    while pendentes:
        pasta = pendentes.pop()
        try:
            with os.scandir(pasta) as entradas:
                for entrada in entradas:
                    if entrada.name.startswith("."):
                        continue
                    try:
                        if entrada.is_dir(follow_symlinks=False):
                            pendentes.append(Path(entrada.path))
                            continue
                        if entrada.is_symlink() and entrada.is_dir(follow_symlinks=True):
                            continue
                    except OSError as exc:
                        if on_error:
                            on_error(exc)
                        else:
                            log.warning("Não consegui inspecionar %s", entrada.path,
                                        exc_info=True)
                        continue
                    if entrada.name.endswith(".assetdeck.json"):
                        continue
                    yield Path(entrada.path)
        except OSError as exc:
            if on_error:
                on_error(exc)
            else:
                log.warning("Não consegui listar a pasta %s", pasta, exc_info=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_library(
    conn: sqlite3.Connection,
    library_id: int,
    root: Path,
    progress: Callable[[int, int, ScanStats], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    batch_size: int = 50,
    workers: int = WORKERS_PADRAO,
) -> ScanStats:
    """Uma passada completa de indexação. Retorna estatísticas do que fez."""
    stats = ScanStats()
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(
            f"A raiz da biblioteca não existe ou não é uma pasta: {root}. "
            "Confira library_root no config.json."
        )

    # Estado atual do banco para esta biblioteca (rel_path → info do arquivo)
    known = {
        row["rel_path"]: row
        for row in conn.execute(
            """SELECT f.id, f.rel_path, f.size_bytes, f.mtime_ns, f.missing_since,
                      f.width, f.phash, f.dominant_color
               FROM files f JOIN assets a ON a.id = f.asset_id
               WHERE a.library_id = ? AND f.deleted_at IS NULL""",
            (library_id,),
        )
    }

    seen: set[str] = set()
    since_commit = 0
    done = 0
    discovered = 0
    walk_had_errors = False
    pool = None
    pool_attempted = False
    stat_pool = ThreadPoolExecutor(max_workers=_STAT_WORKERS,
                                   thread_name_prefix="assetdeck-stat")
    bloco: list[Path] = []
    started_at = time.monotonic()

    def on_walk_error(exc: OSError) -> None:
        nonlocal walk_had_errors
        walk_had_errors = True
        stats.errors += 1
        log.warning("Erro durante a enumeração da biblioteca (%s)", exc,
                    exc_info=(type(exc), exc, exc.__traceback__))

    def processar_bloco(paths: list[Path]) -> None:
        nonlocal pool, pool_attempted, since_commit, done
        if not paths:
            return
        if should_stop and should_stop():
            stats.aborted = True
            return

        def processar_arquivo(path: Path, *, cached_stat=None, cache=None) -> None:
            nonlocal since_commit, done
            if should_stop and should_stop():
                stats.aborted = True
                return
            done += 1
            try:
                _process_file(conn, library_id, root, path, known, seen, stats,
                              cache=cache, cached_stat=cached_stat)
            except OSError:
                # Arquivo ilegível não derruba a varredura, mas fica no log.
                stats.errors += 1
                log.exception("Erro ao ler %s — pulando.", path)

            since_commit += 1
            if since_commit >= batch_size:
                conn.commit()
                since_commit = 0
            if progress and done % 10 == 0:
                # -2 identifica processamento; o total ainda é desconhecido.
                progress(done, -2, stats)
            if done % 500 == 0:
                elapsed = max(time.monotonic() - started_at, 0.001)
                log.info("Varredura: %d arquivo(s) processados (%.1f/s).",
                         done, done / elapsed)

        candidatos: list[Path] = []
        # Arquivos conhecidos e intocados são resolvidos logo após um único
        # stat. Além de cortar uma ida de metadados ao NAS, não ficam esperando
        # o hash de outros arquivos do mesmo bloco terminar.
        avaliar = partial(_avaliar_calculo, root, known=known)
        for path, (precisa, st) in zip(paths, stat_pool.map(avaliar, paths)):
            if precisa:
                candidatos.append(path)
            else:
                processar_arquivo(path, cached_stat=st)
                if stats.aborted:
                    return

        # Reindexações sem arquivos novos/alterados não precisam iniciar os
        # processos filhos, que têm custo de inicialização perceptível.
        if candidatos and not pool_attempted:
            pool = _abrir_pool(workers)
            pool_attempted = True
        if candidatos:
            if progress:
                # -3 identifica espera no cálculo do lote; done é o tamanho
                # do lote, não o total já processado.
                progress(len(candidatos), -3, stats)
            inicio_calculo = time.monotonic()
            log.info("Varredura: calculando fingerprints/metadados de %d arquivo(s).",
                     len(candidatos))
            cache = _pre_calcular(pool, candidatos, should_stop=should_stop)
            log.info("Varredura: lote de cálculo concluído em %.1fs (%d arquivo(s)).",
                     time.monotonic() - inicio_calculo, len(cache))
        else:
            cache = {}
        for path in candidatos:
            processar_arquivo(path, cache=cache)
            if stats.aborted:
                log.warning("Varredura interrompida a pedido (%d arquivos processados).", done)
                break

    try:
        for path in iter_library_files(root, on_error=on_walk_error):
            if should_stop and should_stop():
                stats.aborted = True
                break
            discovered += 1
            bloco.append(path)
            # Também atualiza a tela durante uma enumeração longa. O total
            # ainda é desconhecido até a árvore terminar de ser percorrida.
            if progress and discovered % 100 == 0:
                progress(discovered, -1, stats)
            if discovered % 500 == 0:
                elapsed = max(time.monotonic() - started_at, 0.001)
                log.info("Varredura: %d arquivo(s) descobertos (%.1f/s).",
                         discovered, discovered / elapsed)
            if len(bloco) >= _BLOCO:
                processar_bloco(bloco)
                bloco = []
                if stats.aborted:
                    break
        if not stats.aborted:
            processar_bloco(bloco)
    finally:
        if pool is not None:
            # `cancel_futures` descarta o que ainda não começou — sem isso,
            # fechar no meio da varredura esperava a fila inteira.
            pool.shutdown(wait=True, cancel_futures=True)
        stat_pool.shutdown(wait=True, cancel_futures=True)

    log.info("Varredura de %s: %d arquivos encontrados, %d já no banco.",
             root, discovered, len(known))

    if not stats.aborted and not walk_had_errors:
        # Quem está no banco mas não no disco: marca sumido (nunca apaga)
        for rel_path, row in known.items():
            if rel_path not in seen and row["missing_since"] is None:
                conn.execute(
                    "UPDATE files SET missing_since = ?, updated_at = ? WHERE id = ?",
                    (_now(), _now(), row["id"]),
                )
                stats.missing += 1
                log.warning("Arquivo sumido da biblioteca: %s", rel_path)
    elif walk_had_errors:
        log.warning("Itens sumidos não foram atualizados: a enumeração teve erros.")

    conn.commit()
    if progress:
        # Sinal final: agora o total é conhecido e a barra pode fechar em 100%.
        progress(done, discovered, stats)
    # Índice de busca sempre em dia (barato: milissegundos nessa escala)
    from assetdeck.db.repos.assets import rebuild_fts

    rebuild_fts(conn)
    if stats.ignored_exts:
        log.info("Extensões ignoradas: %s",
                 ", ".join(f".{e} ({n}x)" for e, n in sorted(stats.ignored_exts.items())))
    log.info("Varredura concluída: %s", stats.summary())
    return stats


def _pesado(path: Path, cache: dict | None) -> tuple:
    """Pega do que o pool já calculou; calcula na hora se não estiver lá.

    O fallback não é enfeite: `_precisa_calcular` pode discordar do laço em
    casos de corrida (arquivo mudou entre a decisão e o processamento), e
    aí o certo é calcular, não gravar dado errado."""
    if cache is not None and path in cache:
        return cache[path]
    return calcular_pesado(path)


def _precisa_backfill_imagem(path: Path, row) -> bool:
    from assetdeck.thumbs.raster import RASTER_EXTS

    if path.suffix.lower().lstrip(".") not in RASTER_EXTS:
        return False
    return (row["width"] is None or row["phash"] is None
            or row["dominant_color"] is None)


def _avaliar_calculo(root: Path, path: Path, known: dict):
    """Este arquivo vai exigir hash/metadados nesta passada?

    Decide ANTES de mandar pro pool: arquivo já indexado, do mesmo tamanho,
    mesmo mtime e com os campos preenchidos não precisa de nada — e é a
    maioria numa reindexação. Mandar todos pro pool desperdiçaria a
    paralelização justamente onde ela não é necessária.
    """
    if classify(path) is None:
        return False, None
    try:
        rel = path.relative_to(root).as_posix()
        st = path.stat()
    except OSError:
        return False, None   # ilegível: o laço serial trata e loga
    row = known.get(rel)
    if row is None:
        return True, st                                # novo
    if row["size_bytes"] != st.st_size or row["mtime_ns"] != st.st_mtime_ns:
        return True, st                                # mudou
    precisa = _precisa_backfill_imagem(path, row)
    return precisa, st


def _precisa_calcular(root: Path, path: Path, known: dict) -> bool:
    """Versão booleana mantida para chamadores e testes existentes."""
    precisa, _st = _avaliar_calculo(root, path, known)
    return precisa


def _process_file(conn, library_id, root, path, known, seen, stats,
                  cache: dict | None = None, cached_stat=None) -> None:
    asset_type = classify(path)
    if asset_type is None:
        ext = path.suffix.lower().lstrip(".") or "(sem extensão)"
        stats.ignored += 1
        stats.ignored_exts[ext] = stats.ignored_exts.get(ext, 0) + 1
        return

    rel_path = path.relative_to(root).as_posix()
    seen.add(rel_path)
    st = cached_stat if cached_stat is not None else path.stat()

    row = known.get(rel_path)
    if row is None:
        # Arquivo novo → novo asset (1:1 nesta fatia) + file principal.
        # Se há um sidecar .json ao lado, os metadados voltam do espelho —
        # é o caminho de recuperação quando o banco se perde.
        campos = {
            "uuid": str(uuid_mod.uuid4()), "name": path.stem,
            "rating": None, "starred": 0, "notes": None,
        }
        side = read_sidecar(sidecar_path(path))
        if side:
            recuperados = restorable_fields(side)
            if "uuid" in recuperados and _uuid_livre(conn, recuperados["uuid"]):
                campos["uuid"] = recuperados["uuid"]
            elif "uuid" in recuperados:
                log.warning(
                    "Sidecar de %s traz uuid já usado (arquivo duplicado com "
                    "sidecar copiado?) — gerando uuid novo.", rel_path,
                )
            for k in ("name", "rating", "starred", "notes"):
                if k in recuperados:
                    campos[k] = recuperados[k]
            stats.restored += 1
            log.info("Metadados restaurados do sidecar para %s", rel_path)

        cur = conn.execute(
            """INSERT INTO assets (uuid, library_id, name, asset_type,
                                   rating, starred, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (campos["uuid"], library_id, campos["name"], asset_type,
             campos["rating"], campos["starred"], campos["notes"]),
        )
        if side:
            # Tags do sidecar voltam com cor/ícone de cada elo (Fatia 45) —
            # `_restorable_tags` já normalizou formato 1 (sem cor/ícone) e
            # formato 2 (com) pro mesmo formato de cadeia.
            from assetdeck.db.repos import tags as tags_repo

            for item in restorable_fields(side).get("tags", []):
                tid = tags_repo.get_or_create_chain(conn, item["chain"])
                if tid is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO asset_tags (asset_id, tag_id, source) "
                        "VALUES (?, ?, 'manual')",
                        (cur.lastrowid, tid),
                    )
            # Custom properties do sidecar (Fatia 22) — tipo inferido do
            # valor JSON; datas voltam como texto (simplificação aceitável).
            from assetdeck.db.repos import properties as properties_repo

            for nome, valor in restorable_fields(side).get("custom", {}).items():
                if isinstance(valor, bool):
                    tipo = "bool"
                elif isinstance(valor, (int, float)):
                    tipo = "number"
                else:
                    tipo = "text"
                pid = properties_repo.create_def(conn, nome, tipo)
                properties_repo.set_value(conn, cur.lastrowid, pid, valor)
        impressao, (w, h, alpha, depth, phash, dominant_color) = _pesado(path, cache)
        conn.execute(
            """INSERT INTO files (asset_id, rel_path, size_bytes, mtime_ns,
                                  content_hash, is_primary,
                                  width, height, has_alpha, bit_depth, phash,
                                  dominant_color)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
            (cur.lastrowid, rel_path, st.st_size, st.st_mtime_ns, impressao,
             w, h, alpha, depth, phash, dominant_color),
        )
        stats.added += 1
        return

    if row["size_bytes"] == st.st_size and row["mtime_ns"] == st.st_mtime_ns:
        if _precisa_backfill_imagem(path, row):
            # Backfill: linhas antigas (pré-Fatia 9 / pré-Fatia 20 / pré-Fatia
            # 39) ainda sem dimensões e/ou sem phash e/ou sem cor média
            _fp, (w, h, alpha, depth, phash, dominant_color) = _pesado(path, cache)
            if w is not None:
                conn.execute(
                    "UPDATE files SET width = ?, height = ?, has_alpha = ?, "
                    "bit_depth = ?, phash = ?, dominant_color = ?, "
                    "updated_at = ? WHERE id = ?",
                    (w, h, alpha, depth, phash, dominant_color, _now(), row["id"]),
                )
        if row["missing_since"] is not None:
            # Estava sumido e voltou ao mesmo lugar
            conn.execute(
                "UPDATE files SET missing_since = NULL, updated_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            stats.reappeared += 1
        else:
            stats.unchanged += 1
        return

    # Conteúdo mudou → atualiza medidas e hash (uuid do asset não muda NUNCA)
    impressao, (w, h, alpha, depth, phash, dominant_color) = _pesado(path, cache)
    conn.execute(
        """UPDATE files SET size_bytes = ?, mtime_ns = ?, content_hash = ?,
                            width = ?, height = ?, has_alpha = ?, bit_depth = ?,
                            phash = ?, dominant_color = ?, missing_since = NULL,
                            updated_at = ?
           WHERE id = ?""",
        (st.st_size, st.st_mtime_ns, impressao,
         w, h, alpha, depth, phash, dominant_color, _now(), row["id"]),
    )
    if row["missing_since"] is not None:
        stats.reappeared += 1
    else:
        stats.updated += 1
