from __future__ import annotations

from typing import Any

from persona.store.db import DB, dumps, get_db, loads, new_id, now


def _default_info() -> dict[str, Any]:
    return {
        "chat_history": [],
        "input_messages": [],
        "photo_history": [],
        "future": {"timestamp": None, "action": None, "proactive_times": 0},
    }


def _row(r) -> dict[str, Any] | None:
    if r is None:
        return None
    info = loads(r["info"]) or {}
    base = _default_info()
    base.update(info)
    base.setdefault("future", {}).setdefault("proactive_times", 0)
    return {
        "id": r["id"],
        "kind": r["kind"],
        "participants": loads(r["participants"]),
        "info": base,
        "updated_at": r["updated_at"],
    }


class ConversationStore:
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or get_db()

    def get(self, conv_id: str) -> dict[str, Any] | None:
        return _row(self.db.query_one("SELECT * FROM conversations WHERE id = ?", (conv_id,)))

    def get_or_create_private(self, user_id: str, character_id: str) -> dict[str, Any]:
        pair = sorted([user_id, character_id])
        row = self.db.query_one(
            "SELECT * FROM conversations WHERE kind = 'private' AND participants = ?",
            (dumps(pair),),
        )
        if row:
            return _row(row)  # type: ignore[return-value]
        cid = new_id()
        self.db.execute(
            "INSERT INTO conversations (id, kind, participants, info, updated_at) VALUES (?, 'private', ?, ?, ?)",
            (cid, dumps(pair), dumps(_default_info()), now()),
        )
        return self.get(cid)  # type: ignore[return-value]

    def save_info(self, conv_id: str, info: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE conversations SET info = ?, updated_at = ? WHERE id = ?",
            (dumps(info), now(), conv_id),
        )

    def find_due_future(self, before_ts: int, floor_ts: int) -> list[dict[str, Any]]:
        rows = self.db.query_all("SELECT * FROM conversations WHERE kind = 'private'")
        out: list[dict[str, Any]] = []
        for r in rows:
            conv = _row(r)
            fut = conv["info"].get("future") or {}
            ts = fut.get("timestamp")
            if fut.get("action") and ts and floor_ts < ts < before_ts:
                out.append(conv)
        return out
