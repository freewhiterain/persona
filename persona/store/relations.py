from __future__ import annotations

from typing import Any

from persona.store.db import DB, dumps, get_db, loads, new_id, now


def default_relation() -> dict[str, Any]:
    return {
        "user_info": {"realname": "", "hobbyname": "", "description": "在网上认识的新朋友"},
        "character_info": {
            "longterm_purpose": "慢慢认识新的人，维持自己的生活节奏",
            "shortterm_purpose": "随便聊聊，观察一下这个人",
            "attitude": "略带好奇，有一点戒备",
            "status": "空闲",
        },
        "relationship": {
            "description": "在网上认识的新朋友",
            "closeness": 20,
            "trustness": 20,
            "dislike": 0,
            "status": "空闲",
        },
    }


def _row(r) -> dict[str, Any] | None:
    if r is None:
        return None
    base = default_relation()
    ui = loads(r["user_info"]) or {}
    ci = loads(r["character_info"]) or {}
    rel = loads(r["relationship"]) or {}
    base["user_info"].update(ui)
    base["character_info"].update(ci)
    base["relationship"].update(rel)
    return {
        "id": r["id"],
        "user_id": r["user_id"],
        "character_id": r["character_id"],
        **base,
        "updated_at": r["updated_at"],
    }


class RelationStore:
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or get_db()

    def get(self, user_id: str, character_id: str) -> dict[str, Any] | None:
        return _row(
            self.db.query_one(
                "SELECT * FROM relations WHERE user_id = ? AND character_id = ?",
                (user_id, character_id),
            )
        )

    def get_or_create(self, user_id: str, character_id: str) -> dict[str, Any]:
        existing = self.get(user_id, character_id)
        if existing:
            return existing
        rid = new_id()
        d = default_relation()
        self.db.execute(
            "INSERT INTO relations (id, user_id, character_id, user_info, character_info, relationship, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                rid,
                user_id,
                character_id,
                dumps(d["user_info"]),
                dumps(d["character_info"]),
                dumps(d["relationship"]),
                now(),
            ),
        )
        return self.get(user_id, character_id)  # type: ignore[return-value]

    def save(self, relation: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE relations SET user_info = ?, character_info = ?, relationship = ?, updated_at = ? "
            "WHERE user_id = ? AND character_id = ?",
            (
                dumps(relation["user_info"]),
                dumps(relation["character_info"]),
                dumps(relation["relationship"]),
                now(),
                relation["user_id"],
                relation["character_id"],
            ),
        )

    def all_for_character(self, character_id: str) -> list[dict[str, Any]]:
        rows = self.db.query_all("SELECT * FROM relations WHERE character_id = ?", (character_id,))
        return [_row(r) for r in rows]  # type: ignore[misc]
