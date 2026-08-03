"""Queries de assets. A UI nunca escreve SQL — sempre passa por aqui."""

from __future__ import annotations

import sqlite3

# Tolerância do filtro de cor (Fatia 39): distância euclidiana máxima em RGB
# (escala 0-441) pra considerar "da mesma cor". Calibrado olhando a grade
# real, não só os testes sintéticos — larga o suficiente pra pegar variações
# de iluminação/textura da MESMA cor, apertada o suficiente pra não misturar
# cores vizinhas da paleta.
COLOR_TOLERANCE = 90


def count_active(conn: sqlite3.Connection) -> int:
    """Quantos assets existem (soft-deleted não contam)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM assets WHERE deleted_at IS NULL"
    ).fetchone()
    return row["n"]


def _build_where(
    conn: sqlite3.Connection,
    search: str | None = None,
    asset_types: list[str] | None = None,
    dir_prefix: str | None = None,
    include_subdirs: bool = True,
    tag_id: int | None = None,
    min_rating: int | None = None,
    starred_only: bool = False,
    min_resolution: int | None = None,
    include_hidden: bool = False,
    include_dependencies: bool = True,
    collection_id: int | None = None,
    category_filters: list[dict] | None = None,
    dominant_color: str | None = None,
) -> tuple[str, list]:
    """Trecho de WHERE + params compartilhado por `list_for_grid` e
    `count_by_category` — os dois precisam responder aos MESMOS filtros,
    e duplicar essa lógica é como o contador sai de sincronia com a grade."""
    sql = ""
    params: list = []

    if not include_hidden:
        sql += " AND a.hidden = 0"
    if not include_dependencies:
        sql += " AND a.is_dependency = 0"

    match = _fts_query(search)
    substr_tokens = _substring_tokens(search)
    if match or substr_tokens:
        ramos = []
        if match:
            ramos.append("a.id IN (SELECT rowid FROM assets_fts WHERE assets_fts MATCH ?)")
            params.append(match)
        if substr_tokens:
            sub_sql = " AND ".join("a.name LIKE ? ESCAPE '\\'" for _ in substr_tokens)
            ramos.append(f"a.id IN (SELECT id FROM assets WHERE {sub_sql})")
            params.extend(f"%{_like_escape(t)}%" for t in substr_tokens)
        sql += " AND (" + " OR ".join(ramos) + ")"
    if asset_types:
        sql += f" AND a.asset_type IN ({','.join('?' * len(asset_types))})"
        params.extend(asset_types)
    if category_filters:
        # OR entre categorias, AND entre tipo e extensão DENTRO de cada uma:
        # marcar .fbx em Modelos não pode restringir Imagens a .fbx também.
        grupos = []
        for grupo in category_filters:
            tipos = grupo.get("asset_types") or []
            exts = grupo.get("extensions") or []
            if not tipos:
                continue
            pedaco = f"a.asset_type IN ({','.join('?' * len(tipos))})"
            params.extend(tipos)
            if exts:
                ramos_ext = " OR ".join("lower(f.rel_path) LIKE ?" for _ in exts)
                pedaco += f" AND ({ramos_ext})"
                params.extend(f"%.{e.lower()}" for e in exts)
            grupos.append(f"({pedaco})")
        if grupos:
            sql += " AND (" + " OR ".join(grupos) + ")"
    if tag_id is not None:
        # Filtrar por 'Madeira' inclui assets taggeados nas subtags
        from assetdeck.db.repos import tags as tags_repo

        alvo = tags_repo.descendants(conn, tag_id)
        sql += (f" AND a.id IN (SELECT asset_id FROM asset_tags"
                f" WHERE tag_id IN ({','.join('?' * len(alvo))}))")
        params.extend(alvo)
    if collection_id is not None:
        sql += (" AND a.id IN (SELECT asset_id FROM collection_items"
                " WHERE collection_id = ?)")
        params.append(collection_id)
    if min_rating:
        sql += " AND a.rating >= ?"
        params.append(min_rating)
    if starred_only:
        sql += " AND a.starred = 1"
    if min_resolution:
        # Resolução do arquivo principal; sem dimensões conhecidas = fica de fora
        sql += " AND MAX(COALESCE(f.width, 0), COALESCE(f.height, 0)) >= ?"
        params.append(min_resolution)
    if dominant_color:
        sql += " AND color_distance(f.dominant_color, ?) <= ?"
        params.append(dominant_color)
        params.append(COLOR_TOLERANCE)

    if dir_prefix:
        if include_subdirs:
            sql += " AND f.rel_path LIKE ? ESCAPE '\\'"
            params.append(_like_escape(dir_prefix) + "/%")
        else:
            sql += " AND f.rel_path LIKE ? ESCAPE '\\' AND f.rel_path NOT LIKE ? ESCAPE '\\'"
            params.append(_like_escape(dir_prefix) + "/%")
            params.append(_like_escape(dir_prefix) + "/%/%")
    elif not include_subdirs:
        sql += " AND f.rel_path NOT LIKE '%/%'"  # raiz: só arquivos soltos nela

    return sql, params


def list_for_grid(
    conn: sqlite3.Connection,
    search: str | None = None,
    asset_types: list[str] | None = None,
    dir_prefix: str | None = None,
    include_subdirs: bool = True,
    expand_sets: bool = False,
    tag_id: int | None = None,
    min_rating: int | None = None,
    starred_only: bool = False,
    min_resolution: int | None = None,
    include_hidden: bool = False,
    include_dependencies: bool = True,
    collection_id: int | None = None,
    category_filters: list[dict] | None = None,
    dominant_color: str | None = None,
) -> list[dict]:
    """Assets para a grid (asset + arquivo principal), com filtros combináveis.

    - search: busca por nome via FTS5 (prefixo, sem diferenciar acentos)
    - asset_types: lista de tipos crus ([] ou None = todos). Contrato antigo,
      ainda usado por Smart Collections salvas antes da Fatia 31.
    - category_filters: filtro da barra de categorias (Fatia 31) —
      `[{"asset_types": [...], "extensions": [...]}, ...]`, OR entre grupos,
      AND entre tipo e extensão dentro do grupo. Extensão sem ponto e sem
      diferenciar maiúsculas; lista vazia = todas as daquela categoria.
    - dir_prefix: pasta selecionada na árvore ('' ou None = raiz/tudo)
    - include_subdirs: False = só arquivos diretamente na pasta
    - expand_sets: True = toggle 'agrupar' DESLIGADO — cada mapa de um set
      PBR vira um card próprio (só visualização; o banco não muda)
    - collection_id: só assets dentro dessa coleção, na ORDEM MANUAL em que
      foram arrastados para dentro (Fatia 17)
    - dominant_color: cor (hex) escolhida na paleta fixa de busca por cor
      (Fatia 39) — compara com `files.dominant_color` até `COLOR_TOLERANCE`
      de distância; arquivo sem cor calculada (não-raster) fica de fora
    """
    join_files = ("JOIN files f ON f.asset_id = a.id" if expand_sets
                  else "JOIN files f ON f.asset_id = a.id AND f.is_primary = 1")
    # Capa customizada (Fatia 10). No modo expandido ela é descartada apenas
    # para assets de VÁRIOS arquivos (cada mapa do set mostra a si mesmo);
    # um modelo continua exibindo a capa escolhida — bug relatado pelo Rafael.
    cover_select = ("(SELECT p.file_path FROM previews p WHERE p.asset_id = a.id"
                    " AND p.is_cover = 1 AND p.deleted_at IS NULL LIMIT 1)"
                    " AS cover_path")
    sql = f"""SELECT a.id, a.uuid, a.name, a.asset_type, a.notes,
                    a.rating, a.starred, a.hidden, a.is_dependency,
                    f.rel_path, f.size_bytes, f.content_hash, f.missing_since,
                    f.width, f.height,
                    {cover_select},
                    (SELECT COUNT(*) FROM files f2
                     WHERE f2.asset_id = a.id AND f2.deleted_at IS NULL) AS files_count
             FROM assets a
             {join_files}
             WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL"""

    where, params = _build_where(
        conn, search=search, asset_types=asset_types, dir_prefix=dir_prefix,
        include_subdirs=include_subdirs, tag_id=tag_id, min_rating=min_rating,
        starred_only=starred_only, min_resolution=min_resolution,
        include_hidden=include_hidden, include_dependencies=include_dependencies,
        collection_id=collection_id, category_filters=category_filters,
        dominant_color=dominant_color,
    )
    sql += where

    if collection_id is not None:
        # Ordem manual: a ordem em que os assets foram arrastados para dentro
        sql += (" ORDER BY (SELECT sort_order FROM collection_items"
                " WHERE collection_id = ? AND asset_id = a.id),"
                " a.name COLLATE NOCASE")
        params.append(collection_id)
    else:
        sql += " ORDER BY a.name COLLATE NOCASE, f.rel_path COLLATE NOCASE"
    rows = [dict(r) for r in conn.execute(sql, params)]
    if expand_sets:
        for r in rows:
            if r["files_count"] > 1:
                # Cada mapa do set mostra o próprio nome e o próprio conteúdo
                r["name"] = r["rel_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
                r["cover_path"] = None
    return rows


def list_files(conn: sqlite3.Connection, asset_id: int) -> list[sqlite3.Row]:
    """Arquivos de um asset (para o visualizador de mapas do popup)."""
    return conn.execute(
        """SELECT rel_path, map_role, is_primary, content_hash
           FROM files WHERE asset_id = ? AND deleted_at IS NULL
           ORDER BY is_primary DESC, map_role""",
        (asset_id,),
    ).fetchall()


def distinct_types(conn: sqlite3.Connection) -> list[str]:
    """Tipos de asset presentes no banco (para popular o filtro da UI)."""
    return [
        r["asset_type"]
        for r in conn.execute(
            "SELECT DISTINCT asset_type FROM assets WHERE deleted_at IS NULL ORDER BY 1"
        )
    ]


def extension_counts(conn: sqlite3.Connection,
                     asset_types: list[str] | None = None) -> dict[str, int]:
    """Extensões (sem ponto, minúsculas) do arquivo principal dos assets
    ativos e quantos assets cada uma tem — opcionalmente restrito a uma
    lista de tipos (uma categoria da Fatia 31 pode juntar 2+ tipos)."""
    sql = """SELECT f.rel_path FROM files f
             JOIN assets a ON a.id = f.asset_id
             WHERE f.is_primary = 1 AND f.deleted_at IS NULL AND a.deleted_at IS NULL"""
    params: list = []
    if asset_types:
        sql += f" AND a.asset_type IN ({','.join('?' * len(asset_types))})"
        params.extend(asset_types)
    contagem: dict[str, int] = {}
    for row in conn.execute(sql, params):
        nome = row["rel_path"].rsplit("/", 1)[-1]
        if "." in nome:
            ext = nome.rsplit(".", 1)[-1].lower()
            contagem[ext] = contagem.get(ext, 0) + 1
    return dict(sorted(contagem.items()))


def count_by_category(conn: sqlite3.Connection, categorias, **filtros) -> dict[str, int]:
    """Quantos assets cada categoria tem, respeitando os filtros ATIVOS
    (busca, pasta, tag, nota...) mas ignorando o próprio filtro de
    categoria — senão clicar numa categoria zeraria o contador das outras,
    e o número perde a função de prever o resultado do clique.

    `categorias`: iterável de `ui.categories.Category`."""
    filtros.pop("category_filters", None)
    where, params = _build_where(conn, **filtros)
    sql = f"""SELECT a.asset_type AS t, COUNT(*) AS n FROM assets a
              JOIN files f ON f.asset_id = a.id AND f.is_primary = 1
              WHERE a.deleted_at IS NULL AND f.deleted_at IS NULL{where}
              GROUP BY a.asset_type"""
    por_tipo = {r["t"]: r["n"] for r in conn.execute(sql, params)}
    return {c.key: sum(por_tipo.get(t, 0) for t in c.asset_types) for c in categorias}


def set_rating(conn: sqlite3.Connection, asset_id: int, rating: int | None) -> None:
    """Nota 1–5, ou None = sem nota."""
    from datetime import datetime, timezone

    conn.execute(
        "UPDATE assets SET rating = ?, updated_at = ? WHERE id = ?",
        (rating, datetime.now(timezone.utc).isoformat(), asset_id),
    )
    conn.commit()


def set_starred(conn: sqlite3.Connection, asset_id: int, starred: bool) -> None:
    from datetime import datetime, timezone

    conn.execute(
        "UPDATE assets SET starred = ?, updated_at = ? WHERE id = ?",
        (1 if starred else 0, datetime.now(timezone.utc).isoformat(), asset_id),
    )
    conn.commit()


def set_hidden(conn: sqlite3.Connection, asset_id: int, hidden: bool) -> None:
    """Oculta/reexibe na grade (não é apagar: reversível a qualquer momento)."""
    from datetime import datetime, timezone

    conn.execute(
        "UPDATE assets SET hidden = ?, updated_at = ? WHERE id = ?",
        (1 if hidden else 0, datetime.now(timezone.utc).isoformat(), asset_id),
    )
    conn.commit()


def primary_abs_path(conn: sqlite3.Connection, asset_id: int, library_root) -> "Path | None":
    """Caminho absoluto do arquivo principal do asset (None se sumido)."""
    from pathlib import Path

    row = conn.execute(
        """SELECT f.rel_path, f.missing_since FROM files f
           WHERE f.asset_id = ? AND f.is_primary = 1 AND f.deleted_at IS NULL""",
        (asset_id,),
    ).fetchone()
    if row is None or row["missing_since"] is not None:
        return None
    return Path(library_root) / row["rel_path"]


def set_notes(conn: sqlite3.Connection, asset_id: int, notes: str) -> None:
    """Grava a nota do asset (string vazia = sem nota)."""
    from datetime import datetime, timezone

    conn.execute(
        "UPDATE assets SET notes = ?, updated_at = ? WHERE id = ?",
        (notes or None, datetime.now(timezone.utc).isoformat(), asset_id),
    )
    conn.commit()


def get_bundle(conn: sqlite3.Connection, asset_id: int) -> dict | None:
    """Asset completo para o sidecar: campos + arquivos + tags + custom."""
    a = conn.execute(
        """SELECT id, uuid, name, asset_type, rating, starred, notes
           FROM assets WHERE id = ? AND deleted_at IS NULL""",
        (asset_id,),
    ).fetchone()
    if a is None:
        return None
    files = conn.execute(
        """SELECT rel_path, is_primary FROM files
           WHERE asset_id = ? AND deleted_at IS NULL ORDER BY is_primary DESC""",
        (asset_id,),
    ).fetchall()
    if not files:
        return None
    from assetdeck.db.repos import tags as tags_repo

    tags = [
        tags_repo.tag_path(conn, r["id"])  # caminho completo: sobrevive ao desastre
        for r in tags_repo.tags_of(conn, asset_id)
    ]
    from assetdeck.db.repos import properties as properties_repo

    return {
        "uuid": a["uuid"], "name": a["name"], "asset_type": a["asset_type"],
        "rating": a["rating"], "starred": a["starred"], "notes": a["notes"],
        "tags": tags,
        "custom": properties_repo.values_by_name(conn, asset_id),  # Fatia 22
        "files": [f["rel_path"].rsplit("/", 1)[-1] for f in files],
        "primary_rel_path": files[0]["rel_path"],
    }


def ungroup(conn: sqlite3.Connection, asset_id: int) -> int:
    """Desfaz um agrupamento: cada arquivo vira um asset próprio, TRAVADO
    (group_locked=1) para o agrupador automático nunca refazer. Retorna
    quantos assets novos nasceram."""
    import uuid as uuid_mod
    from datetime import datetime, timezone

    from assetdeck.indexer.scanner import classify  # import tardio: evita ciclo
    from pathlib import Path

    now = datetime.now(timezone.utc).isoformat()
    asset = conn.execute(
        "SELECT library_id FROM assets WHERE id = ? AND deleted_at IS NULL",
        (asset_id,),
    ).fetchone()
    files = conn.execute(
        "SELECT id, rel_path, map_role FROM files "
        "WHERE asset_id = ? AND deleted_at IS NULL",
        (asset_id,),
    ).fetchall()
    if asset is None or len(files) < 2:
        return 0

    for f in files:
        stem = f["rel_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        tipo = classify(Path(f["rel_path"])) or "other"
        cur = conn.execute(
            """INSERT INTO assets (uuid, library_id, name, asset_type, group_locked)
               VALUES (?, ?, ?, ?, 1)""",
            (str(uuid_mod.uuid4()), asset["library_id"], stem, tipo),
        )
        conn.execute(
            "UPDATE files SET asset_id = ?, is_primary = 1, updated_at = ? WHERE id = ?",
            (cur.lastrowid, now, f["id"]),
        )
    conn.execute(
        "UPDATE assets SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, asset_id),
    )
    conn.commit()
    rebuild_fts(conn)
    return len(files)


def group_manual(conn: sqlite3.Connection, asset_ids: list[int]) -> int | None:
    """Funde 2+ assets num set PBR travado (correção manual do Rafael).
    Retorna o id do asset resultante, ou None se não havia o que fundir."""
    from datetime import datetime, timezone

    if len(asset_ids) < 2:
        return None
    now = datetime.now(timezone.utc).isoformat()
    marks = ",".join("?" * len(asset_ids))
    files = conn.execute(
        f"""SELECT f.id, f.asset_id, f.map_role, a.notes
            FROM files f JOIN assets a ON a.id = f.asset_id
            WHERE f.asset_id IN ({marks})
              AND f.deleted_at IS NULL AND a.deleted_at IS NULL""",
        asset_ids,
    ).fetchall()
    if len(files) < 2:
        return None

    # Capa: o basecolor se houver; senão o primeiro arquivo
    principal = next((f for f in files if f["map_role"] == "basecolor"), files[0])
    keeper_id = principal["asset_id"]

    notas = list(dict.fromkeys(f["notes"] for f in files if f["notes"]))
    conn.execute(
        """UPDATE assets SET asset_type = 'pbr_set', group_locked = 1,
                             notes = COALESCE(?, notes), updated_at = ?
           WHERE id = ?""",
        ("\n".join(notas) if notas else None, now, keeper_id),
    )
    for f in files:
        conn.execute(
            "UPDATE files SET asset_id = ?, is_primary = ?, updated_at = ? WHERE id = ?",
            (keeper_id, 1 if f["id"] == principal["id"] else 0, now, f["id"]),
        )
    for aid in asset_ids:
        if aid != keeper_id:
            conn.execute(
                "UPDATE assets SET deleted_at = ?, updated_at = ? WHERE id = ?",
                (now, now, aid),
            )
    conn.commit()
    rebuild_fts(conn)
    return keeper_id


def uuid_exists(conn: sqlite3.Connection, uuid: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM assets WHERE uuid = ?", (uuid,)
    ).fetchone() is not None


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Reconstrói o índice de busca a partir dos assets ativos.

    A coluna `tags` recebe, por asset: nomes das tags dele + ALIASES dessas
    tags + nomes/aliases dos ANCESTRAIS ("madeira" acha o pack taggeado
    "Wood/Oak" via alias PT no pai). É só índice — reconstruível sempre.
    """
    info = {r["id"]: (r["name"], r["parent_id"]) for r in conn.execute(
        "SELECT id, name, parent_id FROM tags WHERE deleted_at IS NULL"
    )}
    apelidos: dict[int, list[str]] = {}
    for r in conn.execute("SELECT tag_id, alias FROM tag_aliases"):
        apelidos.setdefault(r["tag_id"], []).append(r["alias"])

    memo: dict[int, str] = {}

    def texto_da_tag(tid: int) -> str:
        if tid in memo:
            return memo[tid]
        partes: list[str] = []
        atual: int | None = tid
        while atual is not None and atual in info:
            nome, pai = info[atual]
            partes.append(nome)
            partes.extend(apelidos.get(atual, []))
            atual = pai
        memo[tid] = " ".join(partes)
        return memo[tid]

    por_asset: dict[int, list[str]] = {}
    for r in conn.execute("SELECT asset_id, tag_id FROM asset_tags"):
        if r["tag_id"] in info:
            por_asset.setdefault(r["asset_id"], []).append(texto_da_tag(r["tag_id"]))

    conn.execute("INSERT INTO assets_fts(assets_fts) VALUES('delete-all')")
    for row in conn.execute("SELECT id, name FROM assets WHERE deleted_at IS NULL"):
        conn.execute(
            "INSERT INTO assets_fts(rowid, name, tags) VALUES (?, ?, ?)",
            (row["id"], row["name"], " ".join(por_asset.get(row["id"], []))),
        )
    conn.commit()


# Fatia 21: E/OU/NÃO viram os operadores nativos do FTS5 (AND/OR/NOT já
# funcionam com o tokenizer de hoje — testado direto no SQLite do projeto).
_CONECTORES = {"e": "AND", "ou": "OR", "não": "NOT", "nao": "NOT"}


def _fts_query(search: str | None) -> str | None:
    """Texto do usuário → consulta FTS por prefixo ('conc rus' acha 'Concreto
    Rústico'), com E/OU/NÃO virando AND/OR/NOT reais do FTS5.

    Tokeniza e remonta com * — assim caracteres especiais do FTS (aspas,
    dois-pontos…) nunca chegam crus à query.
    """
    if not search:
        return None
    import re

    tokens = re.findall(r"\w+", search, flags=re.UNICODE)
    if not tokens:
        return None
    partes = [_CONECTORES.get(t.lower(), None) or f'"{t}"*' for t in tokens]

    # Conector solto na ponta quebraria a sintaxe do FTS5 — descarta.
    while partes and partes[0] in _CONECTORES.values():
        partes.pop(0)
    while partes and partes[-1] in _CONECTORES.values():
        partes.pop()
    if not partes:
        return None

    # AND implícito entre termos vizinhos sem conector — igual ao
    # comportamento de hoje pra quem não usa E/OU/NÃO.
    resultado = [partes[0]]
    for anterior, atual in zip(partes, partes[1:]):
        conectores = _CONECTORES.values()
        if anterior not in conectores and atual not in conectores:
            resultado.append("AND")
        resultado.append(atual)
    return " ".join(resultado)


def _substring_tokens(search: str | None) -> list[str] | None:
    """Palavras da busca, só quando a frase NÃO usa E/OU/NÃO — servem pra um
    LIKE '%palavra%' extra em assets.name, que pega substring dentro de um
    nome composto sem separador ('quartzite' dentro de 'StoneQuartziteTile',
    onde o FTS por prefixo de palavra não alcança — limitação da Fatia 12).
    Com conector, essa via fica desligada (combinar boolean + substring ao
    mesmo tempo é escopo de uma fatia futura, não desta).
    """
    if not search:
        return None
    import re

    tokens = re.findall(r"\w+", search, flags=re.UNICODE)
    if not tokens or any(t.lower() in _CONECTORES for t in tokens):
        return None
    return tokens


def _like_escape(text: str) -> str:
    """Escapa curingas do LIKE em nomes de pasta ('50%' não pode virar curinga)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
