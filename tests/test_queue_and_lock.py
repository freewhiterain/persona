from __future__ import annotations

import time

from persona.store.locks import LockManager
from persona.store.messages import MessageQueue


def test_lock_mutual_exclusion(db):
    lm = LockManager()
    t1 = lm.acquire("conversation:x", ttl=5)
    assert t1 is not None
    assert lm.acquire("conversation:x", ttl=5, wait=0.0) is None
    assert lm.release("conversation:x", t1) is True
    assert lm.acquire("conversation:x", ttl=5) is not None


def test_lock_expiry_is_swept(db):
    lm = LockManager()
    lm.db.execute(
        "INSERT INTO locks (resource, owner, acquired_ts, expires_ts) VALUES (?,?,?,?)",
        ("conversation:y", "stale", int(time.time()) - 100, int(time.time()) - 10),
    )
    assert lm.acquire("conversation:y", ttl=5) is not None


def test_inbound_batch_and_status(db):
    q = MessageQueue()
    q.add_inbound(from_id="u", to_id="c", body="one")
    q.add_inbound(from_id="u", to_id="c", body="two")
    pend = q.pending_inbound_for("c", max_age=3600)
    assert [m["body"] for m in pend] == ["one", "two"]
    assert q.has_pending_inbound("u", "c") is True

    ids = [m["id"] for m in pend]
    q.set_status_many(ids, "handling")
    assert q.has_pending_inbound("u", "c") is False
    q.set_status_many(ids, "hold")
    assert q.requeue_held("u", "c") == 2
    assert q.has_pending_inbound("u", "c") is True


def test_outbound_due_respects_expect_ts(db):
    q = MessageQueue()
    now = int(time.time())
    q.add_outbound(from_id="c", to_id="u", body="now")
    q.add_outbound(from_id="c", to_id="u", body="later", expect_ts=now + 3600)
    due = q.due_outbound(limit=10)
    assert [m["body"] for m in due] == ["now"]
