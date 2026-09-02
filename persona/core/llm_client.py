"""Thin wrapper over an OpenAI-compatible chat endpoint.

Responsibilities:

* resolve a *model role* ("main" / "fast" / "refine") to a concrete model name
* strip ``<think>...</think>`` blocks (DeepSeek-R1 & friends)
* optional ``response_format={"type": "json_object"}`` for structured calls
* a fully offline ``FakeLLM`` used when ``PERSONA_FAKE_LLM=1`` so the whole
  pipeline (and the test suite) runs with no network
"""

from __future__ import annotations

import json
import re
from typing import Any

from persona.config import Settings, get_settings
from persona.logging_conf import get_logger

logger = get_logger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def extract_json(text: str) -> Any:
    """Best-effort parse of a JSON object/array out of a model reply."""
    raw = strip_think(text).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # brace / bracket extraction fallback
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = raw.find(open_c), raw.rfind(close_c)
        if 0 <= i < j:
            try:
                return json.loads(raw[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"could not parse JSON from model reply: {text[:200]!r}")


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._fake = self.settings.fake_llm
        self._client = None
        if not self._fake:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.env.openai_api_key,
                base_url=self.settings.env.openai_base_url,
            )

    # ------------------------------------------------------------------ #
    def model_for(self, role: str) -> str:
        return self.settings.cfg.models.resolve(role)

    def complete(
        self,
        *,
        system: str,
        user: str,
        role: str = "main",
        json_out: bool = False,
        temperature: float = 0.8,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Return the raw text reply (``<think>`` already stripped)."""
        if self._fake:
            return _FAKE.reply(system=system, user=user, role=role, json_out=json_out)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        params: dict[str, Any] = {
            "model": self.model_for(role),
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            params["max_tokens"] = max_tokens
        if json_out and self.settings.cfg.structured_mode == "json":
            params["response_format"] = {"type": "json_object"}
        if extra:
            params.update(extra)

        resp = self._client.chat.completions.create(**params)  # type: ignore[union-attr]
        return strip_think(resp.choices[0].message.content or "")

    def complete_json(self, *, system: str, user: str, role: str = "main", **kw: Any) -> Any:
        text = self.complete(system=system, user=user, role=role, json_out=True, **kw)
        return extract_json(text)

    # embeddings ------------------------------------------------------------
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        assert not self._fake, "embed() should not be called in fake mode; use HashEmbedder"
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.env.emb_key, base_url=self.settings.env.emb_url)
        resp = client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]


# --------------------------------------------------------------------------- #
# offline stub
# --------------------------------------------------------------------------- #
class FakeLLM:
    """Deterministic canned responses keyed off the requesting agent role/shape."""

    def reply(self, *, system: str, user: str, role: str, json_out: bool) -> str:
        if not json_out:
            # refine agent: return a short in-character line
            return "嗯……我想想。这个我还挺熟的，回头细说。"

        u = user
        if "QueryRewrite" in u or "查询" in u and "关键词" in u:
            return json.dumps(
                {
                    "InnerMonologue": "先想想要查点什么。",
                    "CharacterSettingQueryQuestion": "日常-性格",
                    "CharacterSettingQueryKeywords": "性格,爱好,习惯",
                    "UserProfileQueryQuestion": "对方-基本情况",
                    "UserProfileQueryKeywords": "职业,喜好,近况",
                    "CharacterKnowledgeQueryQuestion": "空",
                    "CharacterKnowledgeQueryKeywords": "空",
                },
                ensure_ascii=False,
            )
        if "总结" in u or "PostAnalyze" in u or "CharacterPublicSettings" in u:
            return json.dumps(
                {
                    "InnerMonologue": "复盘一下这轮对话。",
                    "CharacterPublicSettings": "无",
                    "CharacterPrivateSettings": "聊天记录-初识：对方今天第一次来搭话，聊了几句日常。",
                    "CharacterKnowledges": "无",
                    "UserSettings": "无",
                    "UserRealName": "无",
                    "UserHobbyName": "无",
                    "UserDescription": "刚认识的网友，话不多但还算礼貌。",
                    "CharacterPurpose": "随便聊聊，观察一下这个人。",
                    "CharacterAttitude": "略带好奇。",
                    "RelationDescription": "在网上认识的新朋友",
                    "Dislike": 0,
                },
                ensure_ascii=False,
            )
        # respond agent
        return json.dumps(
            {
                "InnerMonologue": "他发消息过来了，回一句吧。",
                "Reply": "在的<br>刚忙完，怎么了",
                "Segments": [
                    {"type": "text", "content": "在的"},
                    {"type": "text", "content": "刚忙完，怎么了"},
                ],
                "KnowledgeInvolved": "否",
                "RelationDelta": {"Closeness": 1, "Trustness": 0},
                "FutureResponse": {"FutureResponseTime": "无", "FutureResponseAction": "无"},
            },
            ensure_ascii=False,
        )


_FAKE = FakeLLM()

_singleton: LLMClient | None = None


def get_llm() -> LLMClient:
    global _singleton
    if _singleton is None:
        _singleton = LLMClient()
    return _singleton


def reset_llm_cache() -> None:
    global _singleton
    _singleton = None
