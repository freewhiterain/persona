"""ChatPipeline / ProactivePipeline — the multi-agent chain that turns an
inbound turn (or a due proactive action) into reply segments.

    query-rewrite -> memory recall -> respond -> [refine] -> MESSAGE -> post-analyze

The pipeline mutates ``self.context`` in place (relation deltas, booked
future action, recall results); the runner reads it back after the run to
persist.
"""

from __future__ import annotations

import random
from typing import Any, Iterator

from persona.core.agent import AgentStatus, BaseAgent
from persona.logging_conf import get_logger
from persona.memory.retrieval import recall
from persona.chat.agents.post_analyze import PostAnalyzeAgent
from persona.chat.agents.query_rewrite import QueryRewriteAgent
from persona.chat.agents.refine import RefineAgent
from persona.chat.agents.respond import ProactiveRespondAgent, RespondAgent

logger = get_logger(__name__)

DEFAULT_REFINE_CHANCE = 0.12
KNOWLEDGE_REFINE_CHANCE = 0.5


class ChatPipeline(BaseAgent):
    respond_cls = RespondAgent
    #: post-analyze needs both sides of the exchange; proactive has no inbound
    run_post_analyze = True
    #: a real inbound turn clears proactive damping; a proactive run must not
    resets_proactive_damping = True

    def _execute(self) -> Iterator[Any]:
        ctx = self.context

        fut = ctx["conversation"]["info"].setdefault(
            "future", {"timestamp": None, "action": None, "proactive_times": 0}
        )
        if self.resets_proactive_damping:
            fut["proactive_times"] = 0

        # 1. query rewrite --------------------------------------------------
        q = QueryRewriteAgent(ctx).run_to_resp()
        ctx["query"] = q if isinstance(q, dict) else {}

        # 2. memory recall -----------------------------------------------
        ctx["recall"] = recall(
            ctx["query"], character_id=ctx["character"]["id"], user_id=ctx["user"]["id"]
        )

        # 3. respond ----------------------------------------------------
        resp = self.respond_cls(ctx).run_to_resp()
        if not isinstance(resp, dict):
            raise RuntimeError("respond agent produced no result")
        segments: list[dict[str, str]] = resp.get("Segments") or []
        self.resp = resp

        # 4. optional refine -----------------------------------------------
        knowledge = str(resp.get("KnowledgeInvolved", "否")).strip() == "是"
        do_refine = random.random() < DEFAULT_REFINE_CHANCE or (
            knowledge and random.random() < KNOWLEDGE_REFINE_CHANCE
        )
        if do_refine:
            ctx["reply_segments_str"] = _segments_to_str(segments)
            refined = RefineAgent(ctx).run_to_resp()
            if isinstance(refined, list) and refined:
                segments = refined

        ctx["reply_segments_str"] = _segments_to_str(segments)

        # 5. hand the reply to the runner --------------------------------
        self.status = AgentStatus.MESSAGE
        yield {"segments": segments, "resp": resp}

        # 6. post-analyze (memory + relation update) --------------------
        if self.run_post_analyze:
            try:
                PostAnalyzeAgent(ctx).run_to_resp()
            except Exception:  # noqa: BLE001 - non-fatal
                logger.exception("post-analyze failed (continuing)")


class ProactivePipeline(ChatPipeline):
    respond_cls = ProactiveRespondAgent
    run_post_analyze = False
    resets_proactive_damping = False


def _segments_to_str(segments: list[dict[str, str]]) -> str:
    return "\n".join(s.get("content", "") for s in segments)
