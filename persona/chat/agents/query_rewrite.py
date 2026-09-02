from __future__ import annotations

from persona.chat.agents.base import PersonaLLMAgent
from persona.chat.prompts.tasks import SCHEMA_QUERY_REWRITE, TASK_QUERY_REWRITE


class QueryRewriteAgent(PersonaLLMAgent):
    role = "fast"
    temperature = 0.4
    task_template = TASK_QUERY_REWRITE
    output_schema = SCHEMA_QUERY_REWRITE
    context_blocks = ["time", "character", "status", "goal", "relation", "history", "latest"]
