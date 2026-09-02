from __future__ import annotations

from typing import Any

from persona.store.db import DB, dumps, get_db, loads, new_id, now


def _row(r) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "id": r["id"],
        "is_character": bool(r["is_character"]),
        "name": r["name"],
        "display_name": r["display_name"],
        "meta": loads(r["meta"]),
        "created_at": r["created_at"],
    }


class UserStore:
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or get_db()

    def get(self, user_id: str) -> dict[str, Any] | None:
        return _row(self.db.query_one("SELECT * FROM users WHERE id = ?", (user_id,)))

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        return _row(self.db.query_one("SELECT * FROM users WHERE name = ?", (name,)))

    def upsert(
        self,
        *,
        name: str,
        display_name: str | None = None,
        is_character: bool = False,
        meta: dict | None = None,
    ) -> dict[str, Any]:
        existing = self.get_by_name(name)
        if existing:
            if meta is not None:
                self.db.execute(
                    "UPDATE users SET meta = ?, display_name = ? WHERE id = ?",
                    (dumps(meta), display_name or existing["display_name"], existing["id"]),
                )
                return self.get(existing["id"])  # type: ignore[return-value]
            return existing
        uid = new_id()
        self.db.execute(
            "INSERT INTO users (id, is_character, name, display_name, meta, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, int(is_character), name, display_name or name, dumps(meta or {}), now()),
        )
        return self.get(uid)  # type: ignore[return-value]

    def get_or_create_external(
        self, platform: str, external_id: str, display_name: str | None = None
    ) -> dict[str, Any]:
        """A user identified by an id on some transport (e.g. a WeChat wxid).

        Stored as name ``"<platform>:<external_id>"`` with the raw id in meta so
        connectors can look it up on the way back out.
        """
        name = f"{platform}:{external_id}"
        existing = self.get_by_name(name)
        if existing:
            if display_name and display_name != existing["display_name"]:
                self.db.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?", (display_name, existing["id"])
                )
                return self.get(existing["id"])  # type: ignore[return-value]
            return existing
        return self.upsert(
            name=name,
            display_name=display_name or external_id,
            is_character=False,
            meta={"platform": platform, "external_id": external_id},
        )
