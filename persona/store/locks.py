"""Advisory lock backed by a unique row (was luoyun's MongoDBLockManager).

``acquire`` inserts a row keyed by ``resource``; a UNIQUE clash means
someone else holds it.  Expired rows are swept on each attempt so a
crashed holder can't wedge a resource forever.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator

from persona.store.db import DB, get_db, new_id, now


class LockManager:
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or get_db()

    def acquire(self, resource: str, *, ttl: int = 120, wait: float = 0.0, poll: float = 0.25) -> str | None:
        deadline = time.time() + wait
        while True:
            self.db.execute("DELETE FROM locks WHERE expires_ts < ?", (now(),))
            token = new_id()
            try:
                self.db.execute(
                    "INSERT INTO locks (resource, owner, acquired_ts, expires_ts) VALUES (?, ?, ?, ?)",
                    (resource, token, now(), now() + ttl),
                )
                return token
            except sqlite3.IntegrityError:
                if time.time() >= deadline:
                    return None
                time.sleep(poll)

    def release(self, resource: str, token: str | None = None) -> bool:
        if token:
            cur = self.db.execute(
                "DELETE FROM locks WHERE resource = ? AND owner = ?", (resource, token)
            )
        else:
            cur = self.db.execute("DELETE FROM locks WHERE resource = ?", (resource,))
        return cur.rowcount > 0

    @contextmanager
    def lock(self, resource: str, *, ttl: int = 120, wait: float = 0.0) -> Iterator[str | None]:
        token = self.acquire(resource, ttl=ttl, wait=wait)
        try:
            yield token
        finally:
            if token:
                self.release(resource, token)
