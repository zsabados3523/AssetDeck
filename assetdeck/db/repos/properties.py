"""Custom properties: EAV tipado — campos que o Rafael inventa depois
(Fornecedor, Licença…) sem mexer no schema (Fatia 22).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger(__name__)

VALUE_TYPES = ("text", "number", "bool", "date")

_COLUNA_POR_TIPO = {
    "text": "value_text",
    "number": "value_number",
    "bool": "value_bool",
    "date": "value_date",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_def(conn: sqlite3.Connection, name: str, value_type: str) -> int:
    """Cria a definição. `property_defs.name` tem UNIQUE de verdade (não é
    condicional a deleted_at IS NULL como em tags/collections) — então:
    nome ativo já existe → devolve o id; nome existe mas soft-deleted →
    revive em vez de tentar inserir (senão o UNIQUE estoura)."""
    name = name.strip()
    if not name:
        raise ValueError("Nome da propriedade não pode ser vazio.")
    if value_type not in VALUE_TYPES:
        raise ValueError(f"Tipo inválido: {value_type!r} (use {VALUE_TYPES}).")

    row = conn.execute(
        "SELECT id, deleted_at FROM property_defs WHERE name = ?", (name,)
    ).fetchone()
    if row is not None:
        if row["deleted_at"] is None:
            return row["id"]
        conn.execute(
            "UPDATE property_defs SET deleted_at = NULL, created_at = ? WHERE id = ?",
            (_now(), row["id"]),
        )
        conn.commit()
        log.info("Propriedade %r revivida (estava soft-deleted).", name)
        return row["id"]

    cur = conn.execute(
        "INSERT INTO property_defs (name, value_type) VALUES (?, ?)",
        (name, value_type),
    )
    conn.commit()
    log.info("Propriedade criada: %r (%s)", name, value_type)
    return cur.lastrowid


def rename_def(conn: sqlite3.Connection, def_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Nome da propriedade não pode ser vazio.")
    existente = conn.execute(
        "SELECT id FROM property_defs WHERE name = ? AND id != ?", (name, def_id)
    ).fetchone()
    if existente is not None:
        raise ValueError(f"Já existe uma propriedade chamada {name!r}.")
    conn.execute("UPDATE property_defs SET name = ? WHERE id = ?", (name, def_id))
    conn.commit()


def soft_delete_def(conn: sqlite3.Connection, def_id: int) -> None:
    conn.execute(
        "UPDATE property_defs SET deleted_at = ? WHERE id = ?", (_now(), def_id)
    )
    conn.commit()


def list_defs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, name, value_type FROM property_defs
           WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE"""
    ).fetchall()


def set_value(conn: sqlite3.Connection, asset_id: int, property_id: int, value) -> None:
    row = conn.execute(
        "SELECT value_type FROM property_defs WHERE id = ? AND deleted_at IS NULL",
        (property_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Propriedade {property_id} não existe.")
    coluna = _COLUNA_POR_TIPO[row["value_type"]]
    conn.execute(
        f"""INSERT INTO property_values (asset_id, property_id, {coluna})
            VALUES (?, ?, ?)
            ON CONFLICT(asset_id, property_id) DO UPDATE SET {coluna} = excluded.{coluna}""",
        (asset_id, property_id, value),
    )
    conn.commit()


def clear_value(conn: sqlite3.Connection, asset_id: int, property_id: int) -> None:
    conn.execute(
        "DELETE FROM property_values WHERE asset_id = ? AND property_id = ?",
        (asset_id, property_id),
    )
    conn.commit()


def get_values_for_asset(conn: sqlite3.Connection, asset_id: int) -> dict[int, object]:
    """{property_id: valor} — só o que tem valor gravado pra este asset."""
    rows = conn.execute(
        """SELECT property_id, value_text, value_number, value_bool, value_date
           FROM property_values WHERE asset_id = ?""",
        (asset_id,),
    ).fetchall()
    out: dict[int, object] = {}
    for r in rows:
        for coluna in _COLUNA_POR_TIPO.values():
            if r[coluna] is not None:
                out[r["property_id"]] = r[coluna]
                break
    return out


def values_by_name(conn: sqlite3.Connection, asset_id: int) -> dict[str, object]:
    """{nome_da_propriedade: valor} — formato que viaja no sidecar."""
    rows = conn.execute(
        """SELECT d.name, v.value_text, v.value_number, v.value_bool, v.value_date
           FROM property_values v JOIN property_defs d ON d.id = v.property_id
           WHERE v.asset_id = ? AND d.deleted_at IS NULL""",
        (asset_id,),
    ).fetchall()
    out: dict[str, object] = {}
    for r in rows:
        for coluna in _COLUNA_POR_TIPO.values():
            if r[coluna] is not None:
                out[r["name"]] = r[coluna]
                break
    return out
