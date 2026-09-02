"""BaseAgent — a generator-driven unit of work.

Ported clean from luoyun's ``framework/agent/base_agent.py`` idea, minus the
async variant and the half-finished streaming path.  An agent:

* runs ``prehandle -> execute -> posthandle``
* ``yield``s a state dict at each step: ``{agent, status, context, resp}``
* retries the *whole* run up to ``max_retries`` on exception
* can drive a sub-agent with ``yield from sub.run()`` and read the final resp

Consumers iterate ``for state in agent.run(): ...`` and switch on
``state["status"]`` (see :class:`AgentStatus`).  ``FINISHED`` is always the
last state; ``SUCCESS`` carries the good result; ``MESSAGE`` is an
intermediate hand-off (used by the chat pipeline to emit replies before
post-analysis runs).
"""

from __future__ import annotations

import traceback
from enum import Enum
from typing import Any, Iterator

from persona.logging_conf import get_logger

logger = get_logger(__name__)


class AgentStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    MESSAGE = "message"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    ROLLBACK = "rollback"
    CLEAR = "clear"
    FINISHED = "finished"


State = dict[str, Any]


class BaseAgent:
    def __init__(
        self,
        context: dict[str, Any] | None = None,
        *,
        max_retries: int = 2,
        name: str | None = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.max_retries = max_retries
        self.status = AgentStatus.READY
        self.context: dict[str, Any] = context if context is not None else {}
        self.resp: Any = None

    # ------------------------------------------------------------------ #
    # lifecycle hooks (override in subclasses)
    # ------------------------------------------------------------------ #
    def _prehandle(self) -> None: ...

    def _execute(self) -> Iterator[Any]:
        raise NotImplementedError("subclasses must implement _execute")
        yield  # pragma: no cover  (make this a generator)

    def _posthandle(self) -> None: ...

    def _error_handler(self, error: Exception) -> None: ...

    # ------------------------------------------------------------------ #
    # run
    # ------------------------------------------------------------------ #
    def _state(self) -> State:
        return {
            "agent": self.name,
            "status": self.status.value,
            "context": self.context,
            "resp": self.resp,
        }

    def run(self) -> Iterator[State]:
        attempt = 0
        while attempt <= self.max_retries:
            try:
                self.status = AgentStatus.RUNNING
                yield self._state()

                self._prehandle()
                yield self._state()

                for item in self._execute():
                    self.resp = item
                    # an _execute step may set a transient status (e.g. MESSAGE)
                    yield self._state()
                    if self.status is AgentStatus.MESSAGE:
                        self.status = AgentStatus.RUNNING

                self._posthandle()

                self.status = AgentStatus.SUCCESS
                yield self._state()
                self.status = AgentStatus.FINISHED
                yield self._state()
                return

            except Exception as exc:  # noqa: BLE001 - top-level agent guard
                attempt += 1
                self.status = AgentStatus.FAILED
                self.context["error"] = f"{self.name}: {exc}"
                self.context["error_traceback"] = traceback.format_exc()
                logger.error("agent %s failed (attempt %d): %s", self.name, attempt, exc)
                logger.debug("%s", traceback.format_exc())
                try:
                    self._error_handler(exc)
                except Exception:  # noqa: BLE001
                    logger.error("error handler of %s raised:\n%s", self.name, traceback.format_exc())

                if attempt <= self.max_retries:
                    self.status = AgentStatus.RETRYING
                    logger.info("agent %s retrying (%d/%d)", self.name, attempt, self.max_retries)
                    continue

                self.status = AgentStatus.FINISHED
                yield self._state()
                return

    # ------------------------------------------------------------------ #
    # helper for callers that only want the final good resp
    # ------------------------------------------------------------------ #
    def run_to_resp(self) -> Any:
        """Drive the agent to completion, return the last SUCCESS resp (or None)."""
        good: Any = None
        for state in self.run():
            if state["status"] == AgentStatus.SUCCESS.value:
                good = state["resp"]
        return good
