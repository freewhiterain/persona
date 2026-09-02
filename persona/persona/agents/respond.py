from __future__ import annotations

from typing import Any

from persona.persona.agents.base import PersonaLLMAgent, apply_relation_delta, book_future
from persona.persona.prompts.tasks import SCHEMA_RESPOND, TASK_PROACTIVE, TASK_RESPOND


def normalize_segments(resp: dict[str, Any]) -> list[dict[str, str]]:
    """Coerce the model's Segments/Reply into a clean list of text segments."""
    segs = resp.get("Segments")
    out: list[dict[str, str]] = []
    if isinstance(segs, list):
        for s in segs:
            if isinstance(s, dict) and str(s.get("content", "")).strip():
                out.append({"type": "text", "content": str(s["content"]).strip()})
            elif isinstance(s, str) and s.strip():
                out.append({"type": "text", "content": s.strip()})
    if not out:
        reply = str(resp.get("Reply", "")).replace("<br>", "\n").strip()
        for part in filter(None, (p.strip() for p in reply.split("\n"))):
            out.append({"type": "text", "content": part})
    return out or [{"type": "text", "content": "……"}]


class RespondAgent(PersonaLLMAgent):
    role = "main"
    temperature = 0.9
    task_template = TASK_RESPOND
    output_schema = SCHEMA_RESPOND
    context_blocks = [
        "time", "character", "character_profile", "user_profile", "knowledge",
        "status", "goal", "relation", "history", "latest",
    ]

    def _posthandle(self) -> None:
        self.resp["Segments"] = normalize_segments(self.resp)
        apply_relation_delta(self.context, self.resp.get("RelationDelta"))
        book_future(self.context, self.resp.get("FutureResponse"))


class ProactiveRespondAgent(RespondAgent):
    task_template = TASK_PROACTIVE
    context_blocks = [
        "time", "character", "character_profile", "user_profile", "knowledge",
        "status", "goal", "relation", "history", "planned_action",
    ]
