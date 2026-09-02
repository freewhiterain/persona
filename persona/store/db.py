"""SQLite connection + schema.

One file, WAL mode.  Every "collection" from the original Mongo design is a
table here.  JSON-ish blobs (``meta``, ``info``, ``relationship`` ...) are
stored as TEXT and (de)serialised by the DAO helpers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from persona.config import get_settings
from persona.logging_conf import get_logger

logger = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    is_character INTEGER NOT NULL DEFAULT 0,
    name         TEXT NOT NULL,
    display_name TEXT NOT NULL,
    meta         TEXT NOT NULL DEFAULT '{}',
    created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL DEFAULT 'private',
    participants TEXT NOT NULL DEFAULT '[]',
    info         TEXT NOT NULL DEFAULT '{}',
    updated_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    character_id   TEXT NOT NULL,
    user_info      TEXT NOT NULL DEFAULT '{}',
    character_info TEXT NOT NULL DEFAULT '{}',
    relationship   TEXT NOT NULL DEFAULT '{}',
    updated_at     INTEGER NOT NULL,
    UNIQUE (user_id, character_id)
);
CREATE INDEX IF NOT EXISTS ix_relations_char ON relations (character_id);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    direction       TEXT NOT NULL,               -- 'in' | 'out'
    status          TEXT NOT NULL DEFAULT 'pending',
    conversation_id TEXT,
    from_id         TEXT NOT NULL,
    to_id           TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'text', -- text | voice | image
    body            TEXT NOT NULL DEFAULT '',
    meta            TEXT NOT NULL DEFAULT '{}',
    create_ts       INTEGER NOT NULL,
    expect_ts       INTEGER NOT NULL,
    handled_ts      INTEGER
);
CREATE INDEX IF NOT EXISTS ix_messages_inbox
    ON messages (direction, to_id, status, create_ts);
CREATE INDEX IF NOT EXISTS ix_messages_outbox
    ON messages (direction, status, expect_ts);
CREATE INDEX IF NOT EXISTS ix_messages_conv
    ON messages (conversation_id, direction, status);

CREATE TABLE IF NOT EXISTS memories (
    id           TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    user_id      TEXT,
    mtype        TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    key_emb      BLOB,
    value_emb    BLOB,
    meta         TEXT NOT NULL DEFAULT '{}',
    updated_at   INTEGER NOT NULL,
    UNIQUE (character_id, mtype, key)
);
CREATE INDEX IF NOT EXISTS ix_memories_scope ON memories (character_id, mtype);

CREATE TABLE IF NOT EXISTS locks (
    resource    TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    acquired_ts INTEGER NOT NULL,
    expires_ts  INTEGER NOT NULL
);
"""

_local = threading.local()


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> int:
    return int(time.time())


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(text: str | None) -> Any:
    if not text:
        return {}
    return json.loads(text)


class DB:
    """A per-thread SQLite connection holder + tiny query helpers."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else get_settings().db_path

    # connection ---------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        cached: sqlite3.Connection | None = getattr(_local, "conns", {}).get(str(self.path))
        if cached is not None:
            return cached
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        if not hasattr(_local, "conns"):
            _local.conns = {}
        _local.conns[str(self.path)] = conn
        return conn

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)

    # helpers ----------------------------------------------------------
    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()


_db: DB | None = None


def get_db() -> DB:
    global _db
    if _db is None:
        _db = DB()
        _db.init_schema()
    return _db


def reset_db_cache() -> None:
    global _db
    if _db is not None:
        conns = getattr(_local, "conns", {})
        c = conns.pop(str(_db.path), None)
        if c is not None:
            c.close()
    _db = None
