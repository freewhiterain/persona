"""background_handler — time-driven upkeep for one character.

* decay closeness/trustness on an interval
* roll for a proactive-message intent per relationship (affinity-weighted)
* dispatch any due proactive action through :class:`ProactivePipeline`

Busy/idle ("忙闲") switching is left as a manual hook: nothing here changes
``relationship.status`` yet, but the "idle -> requeue held messages" wiring
is kept so a future scheduler module can drive it.
"""

from __future__ import annotations

import random
import time

from persona.config import get_settings
from persona.core.agent import AgentStatus
from persona.logging_conf import get_logger
from persona.chat.context import build_context
from persona.chat.pipeline import ProactivePipeline
from persona.runner.handler import _commit, _stagger
from persona.store.conversations import ConversationStore
from persona.store.locks import LockManager
from persona.store.messages import MessageQueue
from persona.store.relations import RelationStore
from persona.store.users import UserStore

logger = get_logger(__name__)

_PROACTIVE_TOPICS = [
    "挑一件最近关注的事聊聊",
    "聊一个自己擅长的话题",
    "接着之前聊过的话题往下说",
]

_last: dict[str, dict[str, float]] = {}


def _due(character_id: str, key: str, every: int) -> bool:
    now = time.time()
    slot = _last.setdefault(character_id, {})
    if now - slot.get(key, 0.0) >= every:
        slot[key] = now
        return True
    return False


def background_handler(character_id: str) -> None:
    s = get_settings()
    rel_cfg = s.cfg.relations
    users = UserStore()
    if users.get(character_id) is None:
        return

    if _due(character_id, "decay", rel_cfg.decay_every_seconds):
        _decay_all(character_id)

    if _due(character_id, "proactive", rel_cfg.proactive_every_seconds):
        _roll_proactive(character_id, rel_cfg)

    _dispatch_due_future(character_id, s)


def _decay_all(character_id: str) -> None:
    rels = RelationStore()
    for rel in rels.all_for_character(character_id):
        rr = rel["relationship"]
        if rr.get("closeness", 0) > 0 or rr.get("trustness", 0) > 0:
            rr["closeness"] = max(0, rr.get("closeness", 0) - 1)
            rr["trustness"] = max(0, rr.get("trustness", 0) - 1)
            rels.save(rel)
    logger.info("decayed relationships for %s", character_id)


def _roll_proactive(character_id: str, rel_cfg) -> None:
    rels = RelationStore()
    convs = ConversationStore()
    for rel in rels.all_for_character(character_id):
        rr = rel["relationship"]
        if rr.get("dislike", 0) >= rel_cfg.blacklist_dislike:
            continue
        if rr.get("status", "空闲") not in ("空闲",):
            continue
        conv = convs.get_or_create_private(rel["user_id"], character_id)
        fut = conv["info"].get("future") or {}
        if fut.get("action"):
            continue
        score = (rr.get("closeness", 0) + rr.get("trustness", 0)) / 200 + 0.5
        if random.random() > score * rel_cfg.proactive_base_chance:
            continue
        times = fut.get("proactive_times", 0)
        if times > 0 and random.random() > (0.3 ** times):
            continue
        conv["info"].setdefault("future", {})
        conv["info"]["future"].update(
            {"timestamp": int(time.time()), "action": random.choice(_PROACTIVE_TOPICS),
             "proactive_times": times}
        )
        convs.save_info(conv["id"], conv["info"])
        logger.info("booked proactive topic for %s <-> %s", character_id, rel["user_id"])


def _dispatch_due_future(character_id: str, s) -> None:
    convs = ConversationStore()
    rels = RelationStore()
    users = UserStore()
    queue = MessageQueue()
    locks = LockManager()

    now = int(time.time())
    due = convs.find_due_future(before_ts=now, floor_ts=now - 1800)
    due = [c for c in due if character_id in c["participants"]]
    if not due:
        return
    conv = due[0]
    other = next((p for p in conv["participants"] if p != character_id), None)
    if other is None:
        return
    user = users.get(other)
    character = users.get(character_id)
    if user is None or character is None:
        return

    lock_res = f"conversation:{conv['id']}"
    token = locks.acquire(lock_res, ttl=180, wait=0.0)
    if token is None:
        return
    try:
        conv = convs.get(conv["id"])
        relation = rels.get_or_create(user["id"], character_id)
        if relation["relationship"].get("dislike", 0) >= s.cfg.relations.blacklist_dislike:
            conv["info"]["future"] = {"timestamp": None, "action": None,
                                      "proactive_times": conv["info"]["future"].get("proactive_times", 0)}
            convs.save_info(conv["id"], conv["info"])
            return

        conv["info"]["input_messages"] = []
        ctx = build_context(character_row=character, user_row=user,
                            conversation=conv, relation=relation)

        emitted: list[dict] = []
        pipe = ProactivePipeline(ctx)
        for state in pipe.run():
            if state["status"] == AgentStatus.MESSAGE.value:
                segments = state["resp"]["segments"]
                ts = _stagger(segments, typing_speed=s.cfg.runner.typing_speed)
                for seg, when in zip(segments, ts):
                    emitted.append(queue.add_outbound(
                        from_id=character_id, to_id=user["id"], conversation_id=conv["id"],
                        body=seg["content"], kind=seg.get("type", "text"), expect_ts=when,
                    ))
            elif state["status"] == AgentStatus.FAILED.value:
                raise RuntimeError(f"proactive pipeline failed: {ctx.get('error')}")

        fut = ctx["conversation"]["info"].setdefault("future", {})
        fut.update({"timestamp": None, "action": None,
                    "proactive_times": fut.get("proactive_times", 0) + 1})
        _commit(convs, rels, conv, ctx, emitted, [], s)
        logger.info("sent proactive message for %s -> %s", character_id, user["id"])
    except Exception:
        logger.exception("proactive dispatch failed")
    finally:
        locks.release(lock_res, token)
