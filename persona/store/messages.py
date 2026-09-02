"""Unified in/out message queue (was luoyun's inputmessages + outputmessages).

status flow:
  in  : pending -> handling -> handled | hold | failed
  out : pending -> handled | failed
"""

from __future__ import annotations

from typing import Any

from persona.store.db import DB, dumps, get_db, loads, new_id, now


def _row(r) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "id": r["id"],
        "direction": r["direction"],
        "status": r["status"],
        "conversation_id": r["conversation_id"],
        "from_id": r["from_id"],
        "to_id": r["to_id"],
        "kind": r["kind"],
        "body": r["body"],
        "meta": loads(r["meta"]),
        "create_ts": r["create_ts"],
        "expect_ts": r["expect_ts"],
        "handled_ts": r["handled_ts"],
    }


class MessageQueue:
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or get_db()

    # ---- enqueue ----------------------------------------------------------
    def add_inbound(
        self,
        *,
        from_id: str,
        to_id: str,
        body: str,
        kind: str = "text",
        conversation_id: str | None = None,
        meta: dict | None = None,
        create_ts: int | None = None,
    ) -> dict[str, Any]:
        return self._insert(
            direction="in",
            status="pending",
            from_id=from_id,
            to_id=to_id,
            body=body,
            kind=kind,
            conversation_id=conversation_id,
            meta=meta or {},
            create_ts=create_ts or now(),
            expect_ts=create_ts or now(),
        )

    def add_outbound(
        self,
        *,
        from_id: str,
        to_id: str,
        body: str,
        kind: str = "text",
        conversation_id: str | None = None,
        meta: dict | None = None,
        expect_ts: int | None = None,
    ) -> dict[str, Any]:
        t = now()
        return self._insert(
            direction="out",
            status="pending",
            from_id=from_id,
            to_id=to_id,
            body=body,
            kind=kind,
            conversation_id=conversation_id,
            meta=meta or {},
            create_ts=t,
            expect_ts=expect_ts or t,
        )

    def _insert(self, **f: Any) -> dict[str, Any]:
        mid = new_id()
        self.db.execute(
            "INSERT INTO messages "
            "(id, direction, status, conversation_id, from_id, to_id, kind, body, meta, create_ts, expect_ts, handled_ts) "
            "VALUES (:id,:direction,:status,:conversation_id,:from_id,:to_id,:kind,:body,:meta,:create_ts,:expect_ts,NULL)",
            {"id": mid, "meta": dumps(f.pop("meta")), **f},
        )
        return self.get(mid)  # type: ignore[return-value]

    # ---- read -----------------------------------------------------------
    def get(self, mid: str) -> dict[str, Any] | None:
        return _row(self.db.query_one("SELECT * FROM messages WHERE id = ?", (mid,)))

    def pending_inbound_for(self, to_id: str, *, max_age: int, limit: int = 16) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT * FROM messages WHERE direction='in' AND to_id=? AND status='pending' "
            "AND create_ts > ? ORDER BY create_ts ASC LIMIT ?",
            (to_id, now() - max_age, limit),
        )
        return [_row(r) for r in rows]  # type: ignore[misc]

    def inbound_between(self, from_id: str, to_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM messages WHERE direction='in' AND from_id=? AND to_id=?"
        params: list[Any] = [from_id, to_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY create_ts ASC"
        return [_row(r) for r in self.db.query_all(sql, tuple(params))]  # type: ignore[misc]

    def has_pending_inbound(self, from_id: str, to_id: str) -> bool:
        r = self.db.query_one(
            "SELECT 1 FROM messages WHERE direction='in' AND from_id=? AND to_id=? AND status='pending' LIMIT 1",
            (from_id, to_id),
        )
        return r is not None

    def due_outbound(self, limit: int = 1, *, from_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM messages WHERE direction='out' AND status='pending' AND expect_ts <= ?"
        params: list[Any] = [now()]
        if from_id:
            sql += " AND from_id = ?"
            params.append(from_id)
        sql += " ORDER BY expect_ts ASC LIMIT ?"
        params.append(limit)
        return [_row(r) for r in self.db.query_all(sql, tuple(params))]  # type: ignore[misc]

    # ---- mutate -------------------------------------------------------
    def set_status(self, mid: str, status: str, *, handled: bool = False) -> None:
        if handled:
            self.db.execute(
                "UPDATE messages SET status=?, handled_ts=? WHERE id=?", (status, now(), mid)
            )
        else:
            self.db.execute("UPDATE messages SET status=? WHERE id=?", (status, mid))

    def set_status_many(self, ids: list[str], status: str, *, handled: bool = False) -> None:
        for mid in ids:
            self.set_status(mid, status, handled=handled)

    def requeue_held(self, from_id: str, to_id: str) -> int:
        cur = self.db.execute(
            "UPDATE messages SET status='pending' WHERE direction='in' AND from_id=? AND to_id=? AND status='hold'",
            (from_id, to_id),
        )
        return cur.rowcount
