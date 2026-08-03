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
import uuid as uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from assetdeck.sidecar.reader import read_sidecar, restorable_fields
from assetdeck.sidecar.writer import sidecar_path

log = logging.getLogger(__name__)


def _uuid_livre(conn: sqlite3.Connection, uuid: str) -> bool:
    return conn.execute("SELECT 1 FROM assets WHERE uuid = ?", (uuid,)).fetchone() is None


def image_meta(
    path: Path,
) -> tuple[int | None, int | None, int | None, int | None, str | None]:
    """(width, height, has_alpha, bit_depth, phash) numa única abertura do
    arquivo (o phash é barato — só reamostra pra 8x8 — não vale abrir de novo).
    Formatos não-raster ou ilegíveis devolvem tudo None, sem erro."""
    from assetdeck.thumbs.raster import RASTER_EXTS

    if path.suffix.lower().lstrip(".") not in RASTER_EXTS:
        return None, None, None, None, None
    try:
        from assetdeck.thumbs.phash import phash_from_image
        from assetdeck.thumbs.raster import open_image

        with open_image(path) as img:
            has_alpha = 1 if "A" in img.getbands() else 0
            bit_depth = 16 if img.mode.startswith("I;16") else 8
            phash = phash_from_image(img)
            return img.width, img.height, has_alpha, bit_depth, phash
    except Exception:
        log.warning("Não consegui ler o cabeçalho de imagem de %s", path, exc_info=True)
        return None, None, None, None, None

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


def iter_library_files(root: Path):
    """Percorre a biblioteca pulando ocultos e sidecars do próprio AssetDeck."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            if name.startswith(".") or name.endswith(".assetdeck.json"):
                continue
            yield Path(dirpath) / name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_library(
    conn: sqlite3.Connection,
    library_id: int,
    root: Path,
    progress: Callable[[int, int, ScanStats], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    batch_size: int = 50,
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
                      f.width, f.phash
               FROM files f JOIN assets a ON a.id = f.asset_id
               WHERE a.library_id = ? AND f.deleted_at IS NULL""",
            (library_id,),
        )
    }

    paths = list(iter_library_files(root))
    total = len(paths)
    log.info("Varredura de %s: %d arquivos no disco, %d já no banco.",
             root, total, len(known))

    seen: set[str] = set()
    since_commit = 0
    for done, path in enumerate(paths, start=1):
        if should_stop and should_stop():
            stats.aborted = True
            log.warning("Varredura interrompida a pedido (%d/%d processados).", done - 1, total)
            break
        try:
            _process_file(conn, library_id, root, path, known, seen, stats)
        except OSError:
            # Arquivo ilegível não derruba a varredura, mas fica no log.
            stats.errors += 1
            log.exception("Erro ao ler %s — pulando.", path)

        since_commit += 1
        if since_commit >= batch_size:
            conn.commit()
            since_commit = 0
        if progress:
            progress(done, total, stats)

    if not stats.aborted:
        # Quem está no banco mas não no disco: marca sumido (nunca apaga)
        for rel_path, row in known.items():
            if rel_path not in seen and row["missing_since"] is None:
                conn.execute(
                    "UPDATE files SET missing_since = ?, updated_at = ? WHERE id = ?",
                    (_now(), _now(), row["id"]),
                )
                stats.missing += 1
                log.warning("Arquivo sumido da biblioteca: %s", rel_path)

    conn.commit()
    # Índice de busca sempre em dia (barato: milissegundos nessa escala)
    from assetdeck.db.repos.assets import rebuild_fts

    rebuild_fts(conn)
    if stats.ignored_exts:
        log.info("Extensões ignoradas: %s",
                 ", ".join(f".{e} ({n}x)" for e, n in sorted(stats.ignored_exts.items())))
    log.info("Varredura concluída: %s", stats.summary())
    return stats


def _process_file(conn, library_id, root, path, known, seen, stats) -> None:
    asset_type = classify(path)
    if asset_type is None:
        ext = path.suffix.lower().lstrip(".") or "(sem extensão)"
        stats.ignored += 1
        stats.ignored_exts[ext] = stats.ignored_exts.get(ext, 0) + 1
        return

    rel_path = path.relative_to(root).as_posix()
    seen.add(rel_path)
    st = path.stat()

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
        w, h, alpha, depth, phash = image_meta(path)
        conn.execute(
            """INSERT INTO files (asset_id, rel_path, size_bytes, mtime_ns,
                                  content_hash, is_primary,
                                  width, height, has_alpha, bit_depth, phash)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (cur.lastrowid, rel_path, st.st_size, st.st_mtime_ns, fingerprint(path),
             w, h, alpha, depth, phash),
        )
        stats.added += 1
        return

    if row["size_bytes"] == st.st_size and row["mtime_ns"] == st.st_mtime_ns:
        if row["width"] is None or row["phash"] is None:
            # Backfill: linhas antigas (pré-Fatia 9 / pré-Fatia 20) ainda
            # sem dimensões e/ou sem phash
            w, h, alpha, depth, phash = image_meta(path)
            if w is not None:
                conn.execute(
                    "UPDATE files SET width = ?, height = ?, has_alpha = ?, "
                    "bit_depth = ?, phash = ?, updated_at = ? WHERE id = ?",
                    (w, h, alpha, depth, phash, _now(), row["id"]),
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
    w, h, alpha, depth, phash = image_meta(path)
    conn.execute(
        """UPDATE files SET size_bytes = ?, mtime_ns = ?, content_hash = ?,
                            width = ?, height = ?, has_alpha = ?, bit_depth = ?,
                            phash = ?, missing_since = NULL, updated_at = ?
           WHERE id = ?""",
        (st.st_size, st.st_mtime_ns, fingerprint(path),
         w, h, alpha, depth, phash, _now(), row["id"]),
    )
    if row["missing_since"] is not None:
        stats.reappeared += 1
    else:
        stats.updated += 1
