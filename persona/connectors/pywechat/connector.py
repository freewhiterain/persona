"""PyWeChatConnector — bridge the PC WeChat UI and the message queue.

inbound  : poll ``Messages.check_new_messages()`` every ``poll_seconds`` ->
           for each unread text message -> queue.add_inbound
outbound : Connector.run_outbound() (base) -> deliver() ->
           ``Messages.send_messages_to_friend()``

pyweixin drives the single WeChat window, so **every** pyweixin call (poll
and send alike) is serialised behind one lock.  Contacts are addressed by
display name / 备注, which becomes the user's ``external_id``.
"""

from __future__ import annotations

import asyncio
import collections
import threading
from typing import Any

from persona.config import PyWeChatConfig, get_settings
from persona.connectors.base import Connector
from persona.logging_conf import get_logger
from persona.store.users import UserStore

logger = get_logger(__name__)
_PLATFORM = "wechat"

_INSTALL_HINT = (
    "pyweixin not importable (Windows only). See docs/pywechat.md:\n"
    "  1. uv sync --extra wechat-ui        # its runtime deps\n"
    "  2. vendor the package: copy the 'pyweixin' folder from\n"
    "     github.com/Hello-Mr-Crab/pywechat (Mcp/pyweixin_rpa/pyweixin)\n"
    "     into ./vendor/ and add ./vendor to the venv path (a .pth file)."
)


def _load_pyweixin():
    try:
        from pyweixin import Messages  # type: ignore
        from pyweixin.Config import GlobalConfig  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_INSTALL_HINT) from exc
    return Messages, GlobalConfig


class PyWeChatConnector(Connector):
    name = "pywechat"

    def __init__(self, *, character_id: str, cfg: PyWeChatConfig | None = None,
                 prime_on_start: bool = True, **kw: Any) -> None:
        super().__init__(**kw)
        self.cfg = cfg or get_settings().cfg.pywechat
        self.character_id = character_id
        self.outbound_from_id = character_id
        self.users = UserStore()
        self._ui_lock = threading.Lock()
        self._seen: collections.deque[str] = collections.deque(maxlen=self.cfg.dedup_window)
        self._seen_set: set[str] = set()
        self._prime_on_start = prime_on_start
        self._Messages = None
        self._GlobalConfig = None

    # ------------------------------------------------------------------ #
    def _ensure(self) -> None:
        if self._Messages is None:
            self._Messages, self._GlobalConfig = _load_pyweixin()
            # pyweixin defaults: keep WeChat open, don't maximise, gentle pace
            self._GlobalConfig.close_weixin = False
            self._GlobalConfig.is_maximize = False
            self._GlobalConfig.send_delay = max(0.3, self.cfg.send_delay)

    def _key(self, friend: str, m: dict[str, Any]) -> str:
        return f"{friend}\x1f{m.get('消息发送时间', '')}\x1f{m.get('消息内容', '')}"

    def _remember(self, key: str) -> None:
        self._seen.append(key)
        self._seen_set = set(self._seen)

    # ------------------------------------------------------------------ #
    # inbound
    # ------------------------------------------------------------------ #
    async def run_inbound(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure)
        if self._prime_on_start:
            primed = await loop.run_in_executor(None, self._scan, True)
            logger.info("pywechat: primed %d existing unread message(s) (won't reply)", primed)
        logger.info("pywechat: polling every %ss", self.cfg.poll_seconds)
        while True:
            try:
                await loop.run_in_executor(None, self._scan, False)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("pywechat poll failed")
            await asyncio.sleep(self.cfg.poll_seconds)

    def _scan(self, prime_only: bool) -> int:
        """One pass over the session list. Returns count of messages seen."""
        with self._ui_lock:
            batches: dict[str, list[dict]] = self._Messages.check_new_messages(
                search_pages=self.cfg.search_pages, close_weixin=False
            )
        n = 0
        wl = set(self.cfg.whitelist)
        for friend, msgs in (batches or {}).items():
            if wl and friend not in wl:
                continue
            for m in msgs:
                n += 1
                key = self._key(friend, m)
                if key in self._seen_set:
                    continue
                self._remember(key)
                if prime_only:
                    continue
                if str(m.get("消息类型", "")) != "文本":
                    logger.info("pywechat: skip %s message from %s", m.get("消息类型"), friend)
                    continue
                sender = str(m.get("消息发送人", ""))
                if self.cfg.self_name and sender == self.cfg.self_name:
                    continue
                if sender and sender != friend:
                    # group message (sender != chat title) — not handled
                    continue
                body = str(m.get("消息内容", "")).strip()
                if not body:
                    continue
                user = self.users.get_or_create_external(_PLATFORM, friend, friend)
                self.queue.add_inbound(
                    from_id=user["id"], to_id=self.character_id, body=body, kind="text",
                    meta={"pywechat": {"friend": friend, "ts": m.get("消息发送时间")}},
                )
                logger.info("pywechat inbound <- %s: %s", friend, body[:40])
        return n

    # ------------------------------------------------------------------ #
    # outbound
    # ------------------------------------------------------------------ #
    async def deliver(self, message: dict[str, Any]) -> None:
        self._ensure()
        to_user = self.users.get(message["to_id"])
        friend = (to_user or {}).get("meta", {}).get("external_id")
        if not friend:
            raise RuntimeError(f"pywechat: no friend name for user {message['to_id']}")
        body = message["body"]
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send, friend, body)
        logger.info("pywechat delivered -> %s: %s", friend, body[:40])

    def _send(self, friend: str, body: str) -> None:
        with self._ui_lock:
            self._Messages.send_messages_to_friend(
                friend=friend, messages=[body],
                search_pages=self.cfg.search_pages,
                send_delay=self.cfg.send_delay, close_weixin=False,
            )
