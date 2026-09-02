"""WeChatPadProConnector — bridge a self-hosted WeChatPadPro server and the
message queue.

inbound  : ws long-poll  *or*  http webhook  (config ``push_mode``)
           -> adapter.to_std -> filter self/group/dupe -> queue.add_inbound
outbound : Connector.run_outbound() (base) -> deliver() -> client.send_text

Nothing in runner/pipeline changes; this is pure transport.
"""

from __future__ import annotations

import asyncio
import collections
from typing import Any

from persona.config import WeChatPadProConfig, get_settings
from persona.connectors.base import Connector
from persona.connectors.wechatpadpro.adapter import InMsg, iter_push_messages, to_std
from persona.connectors.wechatpadpro.client import WeChatPadClient
from persona.logging_conf import get_logger
from persona.store.users import UserStore

logger = get_logger(__name__)
_PLATFORM = "wechat"


class WeChatPadProConnector(Connector):
    name = "wechatpadpro"

    def __init__(self, *, character_id: str, cfg: WeChatPadProConfig | None = None,
                 token: str | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        s = get_settings()
        self.cfg = cfg or s.cfg.wechatpadpro
        self.token = token or s.wechatpadpro_token
        self.character_id = character_id
        self.outbound_from_id = character_id
        self.users = UserStore()
        self.client = WeChatPadClient(self.cfg, self.token)
        self._seen: collections.deque[str] = collections.deque(maxlen=self.cfg.dedup_window)
        self._seen_set: set[str] = set()

    # ------------------------------------------------------------------ #
    # inbound
    # ------------------------------------------------------------------ #
    async def run_inbound(self) -> None:
        if not self.token:
            raise RuntimeError("wechatpadpro: no token (set WECHATPADPRO_TOKEN or config.toml)")
        if self.cfg.push_mode == "webhook":
            await self._inbound_webhook()
        else:
            await self._inbound_ws()

    async def _ingest(self, raw: dict[str, Any]) -> None:
        msg: InMsg | None = to_std(raw, self_wxid=self.cfg.self_wxid)
        if msg is None or msg.is_self or msg.is_group:
            return
        if msg.msg_id in self._seen_set:
            return
        self._seen.append(msg.msg_id)
        self._seen_set = set(self._seen)

        user = self.users.get_or_create_external(_PLATFORM, msg.from_wxid, msg.nickname)
        self.queue.add_inbound(
            from_id=user["id"],
            to_id=self.character_id,
            body=msg.body,
            kind="text",
            meta={"wechatpadpro": {"msg_id": msg.msg_id, "from_wxid": msg.from_wxid}},
        )
        logger.info("inbound %s <- %s: %s", self.character_id, msg.from_wxid, msg.body[:40])

    async def _inbound_ws(self) -> None:
        import aiohttp

        base = (
            self.cfg.base_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
        )
        url = f"{base}{self.cfg.ws_path}"
        params = {"key": self.token} if self.token else None
        while True:
            try:
                async with aiohttp.ClientSession() as session, session.ws_connect(
                    url, params=params, heartbeat=30
                ) as ws:
                    logger.info("wechatpadpro ws connected: %s", url)
                    async for frame in ws:
                        if frame.type is not aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            import json

                            payload = json.loads(frame.data)
                        except ValueError:
                            continue
                        for raw in iter_push_messages(payload):
                            await self._ingest(raw)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("wechatpadpro ws error; reconnecting in %ss", self.cfg.reconnect_seconds)
                await asyncio.sleep(self.cfg.reconnect_seconds)

    async def _inbound_webhook(self) -> None:
        import hashlib
        import hmac

        from aiohttp import web

        async def handle(request: "web.Request") -> "web.Response":
            body = await request.read()
            if self.cfg.webhook_secret:
                # TODO confirm: header name + whether it's hex or base64
                sig = request.headers.get("X-Signature", request.headers.get("x-wx-signature", ""))
                want = hmac.new(self.cfg.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig, want):
                    return web.Response(status=401, text="bad signature")
            try:
                import json

                payload = json.loads(body)
            except ValueError:
                return web.Response(status=400, text="bad json")
            for raw in iter_push_messages(payload):
                await self._ingest(raw)
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_post(self.cfg.webhook_path, handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.cfg.webhook_host, self.cfg.webhook_port)
        await site.start()
        logger.info(
            "wechatpadpro webhook listening on %s:%s%s",
            self.cfg.webhook_host, self.cfg.webhook_port, self.cfg.webhook_path,
        )
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    # ------------------------------------------------------------------ #
    # outbound
    # ------------------------------------------------------------------ #
    async def deliver(self, message: dict[str, Any]) -> None:
        to_user = self.users.get(message["to_id"])
        wxid = (to_user or {}).get("meta", {}).get("external_id")
        if not wxid:
            raise RuntimeError(f"wechatpadpro: no wxid for user {message['to_id']}")
        kind = message.get("kind", "text")
        if kind == "text":
            await self.client.send_text(wxid, message["body"])
        else:
            logger.warning("wechatpadpro: kind=%s not wired, sending as text", kind)
            await self.client.send_text(wxid, message["body"])
        logger.info("delivered -> %s: %s", wxid, message["body"][:40])
