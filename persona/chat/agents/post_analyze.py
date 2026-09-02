from __future__ import annotations

from persona.config import get_settings
from persona.memory.summarize import ingest_kv_lines
from persona.chat.agents.base import PersonaLLMAgent, _clamp
from persona.chat.prompts.tasks import SCHEMA_POST_ANALYZE, TASK_POST_ANALYZE
from persona.store.memory import MemoryStore


class PostAnalyzeAgent(PersonaLLMAgent):
    """After a reply is emitted: distil new memory rows and update the relation."""

    role = "fast"
    temperature = 0.4
    task_template = TASK_POST_ANALYZE
    output_schema = SCHEMA_POST_ANALYZE
    context_blocks = [
        "time", "character", "character_profile", "user_profile", "knowledge",
        "goal", "relation", "history", "latest_both",
    ]

    def _posthandle(self) -> None:
        r = self.resp
        cid = self.context["character"]["id"]
        uid = self.context["user"]["id"]
        store = MemoryStore()

        ingest_kv_lines(store, r.get("CharacterPublicSettings", "无"),
                        character_id=cid, mtype="character_global")
        ingest_kv_lines(store, r.get("CharacterPrivateSettings", "无"),
                        character_id=cid, mtype="character_private", user_id=uid)
        ingest_kv_lines(store, r.get("CharacterKnowledges", "无"),
                        character_id=cid, mtype="character_knowledge")
        ingest_kv_lines(store, r.get("UserSettings", "无"),
                        character_id=cid, mtype="user_profile", user_id=uid)

        rel = self.context["relation"]
        ui, ci, rr = rel["user_info"], rel["character_info"], rel["relationship"]

        def take(key: str, dst: dict, field: str) -> None:
            val = str(r.get(key, "无")).strip()
            if val and val != "无":
                dst[field] = val

        take("UserRealName", ui, "realname")
        take("UserHobbyName", ui, "hobbyname")
        take("UserDescription", ui, "description")
        take("CharacterPurpose", ci, "shortterm_purpose")
        take("CharacterAttitude", ci, "attitude")
        take("RelationDescription", rr, "description")

        bonus = get_settings().cfg.relations.dislike_analyze_bonus
        try:
            d = int(float(r.get("Dislike", 0) or 0))
        except (TypeError, ValueError):
            d = 0
        # friendly turns still decay dislike; hostile turns add then decay
        rr["dislike"] = _clamp(rr.get("dislike", 0) + d + (bonus if d >= 0 else 0))
