"""LLMAgent — a BaseAgent that renders templated prompts and returns
structured (or free-form) LLM output.

Differences from luoyun's ``BaseSingleRoundLLMAgent``:

* structured output uses **JSON mode** (``response_format`` + tolerant
  parsing) rather than function-calling — portable to local models
* prompt rendering raises a clear error naming the missing context key
* no streaming path
"""

from __future__ import annotations

import string
from typing import Any, Iterator

from persona.core.agent import AgentStatus, BaseAgent
from persona.core.llm_client import LLMClient, get_llm
from persona.logging_conf import get_logger

logger = get_logger(__name__)


class _StrictFormatter(string.Formatter):
    def get_field(self, field_name: str, args: Any, kwargs: Any):  # noqa: ANN401
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise ValueError(f"prompt template references missing field {{{field_name}}}: {exc}") from exc


_FMT = _StrictFormatter()


def render(template: str, context: dict[str, Any]) -> str:
    return _FMT.vformat(template, (), context)


def deep_default(defaults: dict[str, Any], target: dict[str, Any]) -> None:
    """Fill missing keys of ``target`` from ``defaults`` (recursively)."""
    for key, val in defaults.items():
        if key not in target or target[key] is None:
            target[key] = val
        elif isinstance(val, dict) and isinstance(target[key], dict):
            deep_default(val, target[key])


class LLMAgent(BaseAgent):
    #: overridden by subclasses
    system_template: str = ""
    user_template: str = ""
    #: dict of expected output keys -> short description; None = free-form text
    output_schema: dict[str, str] | None = None
    default_input: dict[str, Any] | None = None
    role: str = "main"
    temperature: float = 0.8

    def __init__(
        self,
        context: dict[str, Any] | None = None,
        *,
        llm: LLMClient | None = None,
        max_retries: int = 2,
        name: str | None = None,
    ) -> None:
        super().__init__(context, max_retries=max_retries, name=name)
        self.llm = llm or get_llm()
        self._system = ""
        self._user = ""

    # ------------------------------------------------------------------ #
    def _prehandle(self) -> None:
        if self.default_input:
            deep_default(self.default_input, self.context)
        self._system = render(self.system_template, self.context)
        self._user = render(self.user_template, self.context)
        if self.output_schema:
            self._user += "\n\n" + _schema_instruction(self.output_schema)

    def _execute(self) -> Iterator[Any]:
        if self.output_schema is None:
            text = self.llm.complete(
                system=self._system,
                user=self._user,
                role=self.role,
                temperature=self.temperature,
            )
            yield text
            return

        data = self.llm.complete_json(
            system=self._system,
            user=self._user,
            role=self.role,
            temperature=self.temperature,
        )
        if not isinstance(data, dict):
            raise ValueError(f"{self.name}: expected a JSON object, got {type(data).__name__}")
        # default any missing keys to "无" so posthandlers don't KeyError
        for key in self.output_schema:
            data.setdefault(key, "无")
        yield data


def _schema_instruction(schema: dict[str, str]) -> str:
    lines = [
        "## 输出要求",
        "只输出一个合法 JSON 对象（不要额外文字、不要代码块围栏），包含且仅包含以下字段：",
    ]
    for key, desc in schema.items():
        lines.append(f'- "{key}"：{desc}')
    return "\n".join(lines)
