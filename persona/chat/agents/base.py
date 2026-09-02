"""PersonaLLMAgent — an LLMAgent that assembles its user prompt as

    <task instructions>            (formatted with {character_name}/{user_name})
    ## 上下文
    <context blocks>              (RAW — may contain braces, never .format()'d)
    ## 输出要求
    <schema instruction>          (added by LLMAgent when output_schema set)

The system prompt comes from the active preset (character card override or
global config).
"""

from __future__ import annotations

import random
import time
from typing import Any

from persona.core.llm_agent import LLMAgent, render
from persona.chat.context import parse_cn_time
from persona.chat.prompts import get_system
from persona.chat.prompts import blocks


class PersonaLLMAgent(LLMAgent):
    #: task instruction template (uses {character_name} / {user_name} only)
    task_template: str = ""
    #: ordered block keys from persona.chat.prompts.blocks
    context_blocks: list[str] = []

    def _make_system(self) -> str:
        preset = (self.context.get("character") or {}).get("prompt_preset")
        return get_system(preset)

    def _make_user(self) -> str:
        task = render(self.task_template, self.context)
        section = blocks.build(self.context, self.context_blocks) if self.context_blocks else ""
        return f"{task}\n\n## 上下文\n{section}" if section else task


# --------------------------------------------------------------------------- #
# shared posthandle helpers for reply-producing agents
# --------------------------------------------------------------------------- #
def _clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, v)))


def apply_relation_delta(ctx: dict[str, Any], delta: Any) -> None:
    rel = ctx["relation"]["relationship"]
    try:
        dc = float((delta or {}).get("Closeness", 0) or 0)
        dt = float((delta or {}).get("Trustness", 0) or 0)
    except (TypeError, ValueError):
        dc = dt = 0.0
    rel["closeness"] = _clamp(rel.get("closeness", 0) + dc)
    rel["trustness"] = _clamp(rel.get("trustness", 0) + dt)


def book_future(ctx: dict[str, Any], future_resp: Any) -> None:
    """Probabilistically schedule the next proactive message, damped by how
    many proactive messages we've already sent this conversation."""
    info = ctx["conversation"]["info"]
    fut = info.setdefault("future", {"timestamp": None, "action": None, "proactive_times": 0})
    times = fut.get("proactive_times", 0)
    action = str((future_resp or {}).get("FutureResponseAction", "无")).strip()
    when = parse_cn_time(str((future_resp or {}).get("FutureResponseTime", "无")))

    if action and action != "无" and when and when > int(time.time()):
        if random.random() < (0.25 ** (times + 1) + 0.05):
            fut["timestamp"] = when
            fut["action"] = action
            return
    fut["timestamp"] = None
    fut["action"] = None
