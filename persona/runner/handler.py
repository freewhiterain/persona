"""main_handler — drain pending inbound for one character and produce replies.

Per tick:

1. pick the oldest sender with pending inbound whose conversation we can lock
2. mark that sender's pending inbound as ``handling``
3. build ctx; branch on blacklist / busy-status / normal
4. run :class:`ChatPipeline`; on its MESSAGE hand-off, enqueue reply segments
   with staggered ``expect_ts`` (typing-speed delay)
5. if new inbound arrived mid-run -> rollback (fold everything into history,
   let the next tick reprocess with full context)
6. persist conversation + relation, mark messages handled, release the lock
"""

from __future__ import annotations

import random
import time

from persona.config import get_settings
from persona.core.agent import AgentStatus
from persona.logging_conf import get_logger
from persona.persona.context import build_context
from persona.persona.pipeline import ChatPipeline
from persona.store.conversations import ConversationStore
from persona.store.locks import LockManager
from persona.store.messages import MessageQueue
from persona.store.relations import RelationStore
from persona.store.users import UserStore

logger = get_logger(__name__)


def _stagger(segments: list[dict[str, str]], *, typing_speed: float) -> list[int]:
    """Return an expect_ts per segment, first = now, rest offset by typing time."""
    t = int(time.time())
    out = [t]
    for seg in segments[:-1]:
        gap = max(1, int(len(seg.get("content", "")) / max(typing_speed, 0.1)))
        t += gap + random.randint(0, 2)
        out.append(t)
    return out


def main_handler(character_id: str) -> bool:
    """Process one batch.  Returns True if it did work."""
    s = get_settings()
    users = UserStore()
    convs = ConversationStore()
    rels = RelationStore()
    queue = MessageQueue()
    locks = LockManager()

    character = users.get(character_id)
    if character is None:
        return False

    pending = queue.pending_inbound_for(
        character_id, max_age=s.cfg.runner.max_handle_age, limit=16
    )
    if not pending:
        return False

    # group by sender, oldest first
    sender_id = pending[0]["from_id"]
    user = users.get(sender_id)
    if user is None:
        logger.warning("inbound from unknown user %s, skipping", sender_id)
        queue.set_status_many([m["id"] for m in pending if m["from_id"] == sender_id],
                              "failed", handled=True)
        return True

    conv = convs.get_or_create_private(user["id"], character_id)
    lock_res = f"conversation:{conv['id']}"
    token = locks.acquire(lock_res, ttl=180, wait=0.0)
    if token is None:
        return False  # another worker owns this conversation

    batch = queue.inbound_between(user["id"], character_id, status="pending")
    ids = [m["id"] for m in batch]
    try:
        queue.set_status_many(ids, "handling")

        relation = rels.get_or_create(user["id"], character_id)
        conv = convs.get(conv["id"])  # refresh
        conv["info"]["input_messages"] = batch
        ctx = build_context(
            character_row=character, user_row=user, conversation=conv, relation=relation
        )

        rel_cfg = s.cfg.relations
        emitted: list[dict] = []

        # --- blacklist -------------------------------------------------
        if relation["relationship"].get("dislike", 0) >= rel_cfg.blacklist_dislike:
            queue.add_outbound(
                from_id=character_id, to_id=user["id"], conversation_id=conv["id"],
                body="[系统] 对方已被拉黑。",
            )
            _commit(convs, rels, conv, ctx, emitted, batch, s)
            queue.set_status_many(ids, "handled", handled=True)
            return True

        # --- busy: hold ----------------------------------------------
        if relation["relationship"].get("status", "空闲") not in ("空闲",):
            logger.info("character busy (%s) - holding %d message(s)",
                        relation["relationship"].get("status"), len(ids))
            queue.set_status_many(ids, "hold")
            return True

        # --- normal pipeline ---------------------------------------------
        rolled_back = False
        pipe = ChatPipeline(ctx)
        for state in pipe.run():
            if queue.has_pending_inbound(user["id"], character_id):
                rolled_back = True
                logger.info("rollback: new inbound arrived mid-run")
                break
            if state["status"] == AgentStatus.MESSAGE.value:
                segments = state["resp"]["segments"]
                ts = _stagger(segments, typing_speed=s.cfg.runner.typing_speed)
                for seg, when in zip(segments, ts):
                    out = queue.add_outbound(
                        from_id=character_id, to_id=user["id"], conversation_id=conv["id"],
                        body=seg["content"], kind=seg.get("type", "text"), expect_ts=when,
                    )
                    emitted.append(out)
            elif state["status"] == AgentStatus.FAILED.value:
                raise RuntimeError(f"pipeline failed: {ctx.get('error')}")

        _commit(convs, rels, conv, ctx, emitted, batch, s)
        queue.set_status_many(ids, "handled", handled=True)
        if rolled_back:
            logger.info("rolled back; %d new message(s) will be picked up next tick",
                        1)
        return True

    except Exception:
        logger.exception("main_handler failed for %s", character_id)
        queue.set_status_many(ids, "failed", handled=True)
        return True
    finally:
        locks.release(lock_res, token)


def _commit(convs, rels, conv, ctx, emitted, batch, s) -> None:
    info = conv["info"]
    history = info.get("chat_history", [])
    history.extend(batch)
    history.extend(emitted)
    info["chat_history"] = history[-s.cfg.runner.max_history :]
    info["input_messages"] = []
    convs.save_info(conv["id"], info)
    rels.save(ctx["relation"])
