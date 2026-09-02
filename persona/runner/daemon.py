"""Async daemon: run main_handler + background_handler on a fixed tick.

The handlers are synchronous (blocking SQLite + LLM calls) so they run in a
thread executor; the loops themselves just pace and supervise.
"""

from __future__ import annotations

import asyncio
import traceback

from persona.config import get_settings
from persona.logging_conf import get_logger
from persona.runner.background import background_handler
from persona.runner.handler import main_handler

logger = get_logger(__name__)


async def _loop(fn, character_id: str, tick: float, *, label: str) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, fn, character_id)
        except Exception:  # noqa: BLE001
            logger.error("%s loop error:\n%s", label, traceback.format_exc())
        await asyncio.sleep(tick)


async def run_daemon(character_id: str) -> None:
    tick = get_settings().cfg.runner.tick_seconds
    logger.info("daemon up for character=%s tick=%ss", character_id, tick)
    await asyncio.gather(
        _loop(main_handler, character_id, tick, label="handler"),
        _loop(background_handler, character_id, max(tick, 2.0), label="background"),
    )
