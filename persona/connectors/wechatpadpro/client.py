"""HTTP client for WeChatPadPro's send APIs.

``aiohttp`` is imported lazily so the base package installs without it.
Paths / payloads are confirmed against WeChatPadPro ``/docs/swagger.json``
(v860): base ``/``, auth ``?key=<token>``, text send is
``POST /message/SendTextMessage`` with ``{"MsgItem": [MessageItem]}``.
"""

from __future__ import annotations

from typing import Any

from persona.config import WeChatPadProConfig
from persona.logging_conf import get_logger

logger = get_logger(__name__)


class WeChatPadClient:
    def __init__(self, cfg: WeChatPadProConfig, token: str) -> None:
        self.base = cfg.base_url.rstrip("/")
        self.token = token
        self.cfg = cfg
        self._session: Any = None

    async def _session_get(self):
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = await self._session_get()
        url = f"{self.base}{path}"
        params = {"key": self.token} if self.token else None  # WeChatPadPro: ?key=<token>
        async with session.post(url, json=payload, params=params, timeout=30) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"wechatpadpro {path} -> HTTP {resp.status}: {text[:300]}")
            try:
                import json

                return json.loads(text)
            except ValueError:
                return {"raw": text}

    # -- send ------------------------------------------------------------
    async def send_text(self, to_wxid: str, content: str) -> dict[str, Any]:
        # POST /message/SendTextMessage?key=<token>
        # body: {"MsgItem": [{"ToUserName","TextContent","MsgType":1,"AtWxIDList":[]}]}
        payload = {
            "MsgItem": [
                {"ToUserName": to_wxid, "TextContent": content, "MsgType": 1, "AtWxIDList": []}
            ]
        }
        return await self._post(self.cfg.send_text_path, payload)

    async def send_image(self, to_wxid: str, image_b64: str) -> dict[str, Any]:
        # same SendMessageModel: MsgType 2 + ImageContent (base64) via SendImageMessage
        raise NotImplementedError("wechatpadpro send_image: wire once text works")

    async def send_voice(self, to_wxid: str, voice_ref: str, seconds: int) -> dict[str, Any]:
        raise NotImplementedError("wechatpadpro send_voice: wire once text works")

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
