"""memories table: CRUD + vector / keyword primitives.

mtype in:
  character_global    - public persona facts
  character_private   - persona facts private to one user (needs user_id)
  user_profile        - facts about the user (needs user_id)
  character_knowledge - things the persona has learned
  character_photo     - reserved for future multimodal
"""

from __future__ import annotations

from typing import Any

import numpy as np

from persona.memory.embedder import Embedder, get_embedder
from persona.store.db import DB, dumps, get_db, loads, new_id, now
from persona.store.vector import from_blob, rank, to_blob

MTYPES = (
    "character_global",
    "character_private",
    "user_profile",
    "character_knowledge",
    "character_photo",
)
_USER_SCOPED = {"character_private", "user_profile"}


def _row(r) -> dict[str, Any]:
    return {
        "id": r["id"],
        "character_id": r["character_id"],
        "user_id": r["user_id"],
        "mtype": r["mtype"],
        "key": r["key"],
        "value": r["value"],
        "meta": loads(r["meta"]),
        "updated_at": r["updated_at"],
    }


class MemoryStore:
    def __init__(self, db: DB | None = None, embedder: Embedder | None = None) -> None:
        self.db = db or get_db()
        self.embedder = embedder or get_embedder()

    # ---- write --------------------------------------------------------
    def upsert(
        self,
        *,
        character_id: str,
        mtype: str,
        key: str,
        value: str,
        user_id: str | None = None,
        meta: dict | None = None,
    ) -> str:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError("memory key/value must be non-empty")
        if mtype in _USER_SCOPED and not user_id:
            raise ValueError(f"mtype {mtype} requires user_id")

        key_emb, value_emb = self.embedder.embed([key, value])
        existing = self.db.query_one(
            "SELECT id FROM memories WHERE character_id=? AND mtype=? AND key=?",
            (character_id, mtype, key),
        )
        if existing:
            self.db.execute(
                "UPDATE memories SET value=?, key_emb=?, value_emb=?, meta=?, updated_at=?, user_id=? WHERE id=?",
                (value, to_blob(key_emb), to_blob(value_emb), dumps(meta or {}), now(), user_id, existing["id"]),
            )
            return existing["id"]
        mid = new_id()
        self.db.execute(
            "INSERT INTO memories (id, character_id, user_id, mtype, key, value, key_emb, value_emb, meta, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (mid, character_id, user_id, mtype, key, value,
             to_blob(key_emb), to_blob(value_emb), dumps(meta or {}), now()),
        )
        return mid

    def delete(self, mid: str) -> bool:
        return self.db.execute("DELETE FROM memories WHERE id=?", (mid,)).rowcount > 0

    def get(self, mid: str) -> dict[str, Any] | None:
        r = self.db.query_one("SELECT * FROM memories WHERE id=?", (mid,))
        return _row(r) if r else None

    def count(self, character_id: str, mtype: str) -> int:
        r = self.db.query_one(
            "SELECT COUNT(*) c FROM memories WHERE character_id=? AND mtype=?", (character_id, mtype)
        )
        return int(r["c"])

    # ---- read --------------------------------------------------------
    def _candidates(self, character_id: str, mtype: str, user_id: str | None) -> list:
        sql = "SELECT * FROM memories WHERE character_id=? AND mtype=?"
        params: list[Any] = [character_id, mtype]
        if mtype in _USER_SCOPED:
            sql += " AND user_id=?"
            params.append(user_id)
        return self.db.query_all(sql, tuple(params))

    def vector_search(
        self,
        *,
        character_id: str,
        mtype: str,
        query_vec: list[float],
        field: str,  # "key_emb" | "value_emb"
        user_id: str | None = None,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        rows = self._candidates(character_id, mtype, user_id)
        pairs = [(r["id"], from_blob(r[field])) for r in rows]
        q = np.asarray(query_vec, dtype=np.float32)
        ranked = rank(q, [(rid, emb) for rid, emb in pairs if emb is not None], top_k)
        by_id = {r["id"]: r for r in rows}
        return [{**_row(by_id[rid]), "similarity": sim} for rid, sim in ranked]

    def keyword_search(
        self,
        *,
        character_id: str,
        mtype: str,
        field: str,  # "key" | "value"
        keywords: list[str],
        user_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for kw in keywords:
            kw = kw.strip()
            if not kw or kw == "空":
                continue
            sql = f"SELECT * FROM memories WHERE character_id=? AND mtype=? AND {field} LIKE ?"
            params: list[Any] = [character_id, mtype, f"%{kw}%"]
            if mtype in _USER_SCOPED:
                sql += " AND user_id=?"
                params.append(user_id)
            sql += " LIMIT ?"
            params.append(limit)
            for r in self.db.query_all(sql, tuple(params)):
                if r["id"] not in seen:
                    seen.add(r["id"])
                    out.append(_row(r))
        return out

    def list_all(self, character_id: str, mtype: str) -> list[dict[str, Any]]:
        return [_row(r) for r in self._candidates(character_id, mtype, None)]
