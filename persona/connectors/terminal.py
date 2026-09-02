"""Terminal connector: stdin -> inbound queue, due outbound -> stdout."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from persona.connectors.base import Connector
from persona.logging_conf import get_logger

logger = get_logger(__name__)


class TerminalConnector(Connector):
    name = "terminal"

    def __init__(self, *, user_id: str, user_name: str, character_id: str,
                 character_name: str, **kw: Any) -> None:
        super().__init__(**kw)
        self.user_id = user_id
        self.user_name = user_name
        self.character_id = character_id
        self.character_name = character_name

    async def run_inbound(self, *, eof_grace: float = 30.0) -> None:
        loop = asyncio.get_running_loop()
        print(f"— 与 {self.character_name} 的对话已开始，直接输入即可（Ctrl+C 退出）—\n", flush=True)
        while True:
            try:
                line = await loop.run_in_executor(None, self._read)
            except EOFError:
                # piped input / Ctrl+D: stop reading, let queued replies flush, then exit
                await asyncio.sleep(eof_grace)
                return
            if not line or not line.strip():
                continue
            self.queue.add_inbound(
                from_id=self.user_id, to_id=self.character_id, body=line.strip(), kind="text"
            )

    def _read(self) -> str:
        return input(f"{self.user_name}: ")

    async def deliver(self, message: dict[str, Any]) -> None:
        prefix = "🎤 " if message["kind"] == "voice" else ""
        sys.stdout.write(f"\r{self.character_name}: {prefix}{message['body']}\n{self.user_name}: ")
        sys.stdout.flush()
