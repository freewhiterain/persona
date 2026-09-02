from __future__ import annotations

from persona.persona.context import build_context, parse_cn_time
from persona.persona.pipeline import ChatPipeline
from persona.runner.handler import main_handler
from persona.store.conversations import ConversationStore
from persona.store.messages import MessageQueue
from persona.store.relations import RelationStore


def test_parse_cn_time_roundtrips():
    assert parse_cn_time("无") is None
    assert parse_cn_time("2030年01月02日03时04分") is not None
    assert parse_cn_time("random text") is None


def test_pipeline_produces_segments_and_updates_relation(seeded):
    lin, me = seeded
    convs, rels = ConversationStore(), RelationStore()
    conv = convs.get_or_create_private(me["id"], lin["id"])
    conv["info"]["input_messages"] = [
        MessageQueue().add_inbound(from_id=me["id"], to_id=lin["id"], body="在吗")
    ]
    rel = rels.get_or_create(me["id"], lin["id"])
    ctx = build_context(character_row=lin, user_row=me, conversation=conv, relation=rel)

    before = ctx["relation"]["relationship"]["closeness"]
    msgs = [s for s in ChatPipeline(ctx).run() if s["status"] == "message"]
    assert msgs and msgs[0]["resp"]["segments"]
    assert all(seg["type"] == "text" and seg["content"] for seg in msgs[0]["resp"]["segments"])
    # FakeLLM respond returns Closeness +1
    assert ctx["relation"]["relationship"]["closeness"] == before + 1


def test_main_handler_full_turn(seeded):
    lin, me = seeded
    q = MessageQueue()
    q.add_inbound(from_id=me["id"], to_id=lin["id"], body="你好，问个事")

    assert main_handler(lin["id"]) is True

    outs = q.db.query_all(
        "SELECT body FROM messages WHERE direction='out' AND to_id=? ORDER BY expect_ts", (me["id"],)
    )
    assert len(outs) >= 1

    # inbound consumed
    assert q.has_pending_inbound(me["id"], lin["id"]) is False
    remaining = q.db.query_one(
        "SELECT status FROM messages WHERE direction='in' AND from_id=?", (me["id"],)
    )
    assert remaining["status"] == "handled"

    # history got both sides
    conv = ConversationStore().get_or_create_private(me["id"], lin["id"])
    assert len(conv["info"]["chat_history"]) >= 2


def test_blacklist_short_circuits(seeded):
    lin, me = seeded
    rels = RelationStore()
    rel = rels.get_or_create(me["id"], lin["id"])
    rel["relationship"]["dislike"] = 100
    rels.save(rel)

    q = MessageQueue()
    q.add_inbound(from_id=me["id"], to_id=lin["id"], body="hi")
    assert main_handler(lin["id"]) is True
    outs = q.db.query_all("SELECT body FROM messages WHERE direction='out'")
    assert len(outs) == 1 and "拉黑" in outs[0]["body"]


def test_busy_status_holds_messages(seeded):
    lin, me = seeded
    rels = RelationStore()
    rel = rels.get_or_create(me["id"], lin["id"])
    rel["relationship"]["status"] = "睡觉"
    rels.save(rel)

    q = MessageQueue()
    q.add_inbound(from_id=me["id"], to_id=lin["id"], body="在吗")
    assert main_handler(lin["id"]) is True

    held = q.db.query_one("SELECT status FROM messages WHERE direction='in' AND from_id=?", (me["id"],))
    assert held["status"] == "hold"
    assert q.db.query_all("SELECT 1 FROM messages WHERE direction='out'") == []
