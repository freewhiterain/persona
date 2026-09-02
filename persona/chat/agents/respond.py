from __future__ import annotations

import json
import re
from typing import Any

from persona.chat.agents.base import PersonaLLMAgent, apply_relation_delta, book_future
from persona.chat.prompts.tasks import SCHEMA_RESPOND, TASK_PROACTIVE, TASK_RESPOND
from persona.core.llm_client import extract_json

# lines that are JSON scaffolding a weak model leaked into the segment list
_JSON_NOISE = re.compile(
    r'^\s*(?:[{}\[\],]+|"?(?:type|content|emotion)"?\s*:\s*"?(?:text|voice|photo)?"?,?)\s*$',
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return text.strip().strip("{}[]").strip().strip('",').strip()


def _pull_contents(obj: Any) -> list[str]:
    """Recursively collect 'content' values from parsed JSON."""
    found: list[str] = []
    if isinstance(obj, dict):
        c = obj.get("content")
        if isinstance(c, str) and c.strip():
            found.append(c.strip())
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found += _pull_contents(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _pull_contents(v)
    return found


def normalize_segments(resp: dict[str, Any]) -> list[dict[str, str]]:
    """Coerce the model's Segments/Reply into a clean list of text segments.

    Weak local models sometimes emit the JSON of the segment array *as text*
    (leaking ``{``, ``"type": "text"`` ... as separate items), so we detect
    that, re-parse, and pull the real ``content`` strings out.
    """
    raw: list[str] = []
    segs = resp.get("Segments")
    if isinstance(segs, list):
        for s in segs:
            if isinstance(s, dict) and str(s.get("content", "")).strip():
                raw.append(str(s["content"]).strip())
            elif isinstance(s, str) and s.strip():
                raw.append(s.strip())
    elif isinstance(segs, str) and segs.strip():
        raw.append(segs.strip())

    if not raw:
        reply = str(resp.get("Reply", "")).replace("<br>", "\n").strip()
        raw = [p.strip() for p in reply.split("\n") if p.strip()]

    blob = "\n".join(raw)
    leaked = ('"content"' in blob and '"type"' in blob) or blob.lstrip().startswith(("[", "{"))
    if leaked:
        try:
            contents = _pull_contents(extract_json(blob))
        except (ValueError, json.JSONDecodeError):
            contents = []
        if contents:
            raw = contents
            leaked = False  # recovered clean strings

    out: list[dict[str, str]] = []
    for item in raw:
        if _JSON_NOISE.match(item):  # pure JSON scaffolding, always drop
            continue
        cleaned = _clean(item) if leaked else item.strip()
        if cleaned:
            out.append({"type": "text", "content": cleaned})
    if not out and raw:  # last resort: keep whatever non-empty text we had
        joined = " ".join(x.strip() for x in raw if x.strip())
        if joined:
            out = [{"type": "text", "content": joined}]
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
