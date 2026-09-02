"""Connector interface.

A connector bridges some transport (a terminal, an IM webhook, ...) and the
message queue:

* inbound  transport event  -> ``MessageQueue.add_inbound``
* due outbound message      -> deliver on the transport, then mark handled

Only :class:`TerminalConnector` ships today; the ABC exists so an IM
connector can be dropped in without touching the runner.
"""

from __future__ import annotations

import abc
from typing import Any

from persona.store.messages import MessageQueue


class Connector(abc.ABC):
    name = "base"

    def __init__(self, *, queue: MessageQueue | None = None) -> None:
        self.queue = queue or MessageQueue()

    @abc.abstractmethod
    async def run_inbound(self) -> None:
        """Loop: read transport events, enqueue them as inbound messages."""

    @abc.abstractmethod
    async def deliver(self, message: dict[str, Any]) -> None:
        """Send one outbound message on the transport."""

    async def run_outbound(self, *, poll: float = 0.3) -> None:
        import asyncio

        while True:
            for msg in self.queue.due_outbound(limit=10):
                try:
                    await self.deliver(msg)
                    self.queue.set_status(msg["id"], "handled", handled=True)
                except Exception:  # noqa: BLE001
                    self.queue.set_status(msg["id"], "failed", handled=True)
            await asyncio.sleep(poll)
