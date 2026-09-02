from __future__ import annotations

from persona.core.llm_client import extract_json
from persona.chat.agents.base import PersonaLLMAgent
from persona.chat.agents.respond import normalize_segments
from persona.chat.prompts.tasks import TASK_REFINE


class RefineAgent(PersonaLLMAgent):
    """Free-form rewrite of the draft segments using the 'refine' model role.

    ``resp`` is set to a cleaned list of text segments.
    """

    role = "refine"
    temperature = 0.85
    task_template = TASK_REFINE
    output_schema = None
    context_blocks = [
        "time", "character", "character_profile", "knowledge",
        "relation", "history", "latest", "draft_reply",
    ]

    def _posthandle(self) -> None:
        raw = self.resp
        try:
            data = extract_json(raw) if isinstance(raw, str) else raw
        except ValueError:
            data = None
        if isinstance(data, list):
            self.resp = normalize_segments({"Segments": data})
        elif isinstance(data, dict):
            self.resp = normalize_segments(data)
        else:
            text = str(raw).replace("<br>", "\n")
            self.resp = normalize_segments({"Reply": text})
