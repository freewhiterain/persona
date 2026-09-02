"""WeChatPadPro push envelope  ->  standard inbound message.

The pad-protocol family (WeChatPadPro / wechat-pad-pro / ipad) wraps fields
inconsistently across builds and versions:  ``FromUserName`` may be a bare
string or ``{"string": "wxid_x"}``;  the message list key may be ``AddMsgs``,
``add_msgs``, ``MsgList`` ...  This module normalises the common shapes and
leaves the rest as ``TODO confirm``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

# WeChat MsgType -> our coarse kind
_TYPE_MAP = {
    1: "text",
    3: "image",
    34: "voice",
    43: "video",
    47: "sticker",
    49: "reference",  # app msg / quoted reply / link / file
    10000: "system",
}

_MSG_LIST_KEYS = ("AddMsgs", "add_msgs", "AddMsgList", "MsgList", "messages", "data", "Data")
_MSGID_KEYS = ("msgId", "MsgId", "msg_id", "msgid", "newMsgId", "NewMsgId", "newMsgID")
# fields that mark a bare dict as a single message (WeChatPadPro webhook body)
_SINGLE_MARKERS = (*_MSGID_KEYS, "msgType", "MsgType", "msg_type", "content", "Content")


def _unwrap(v: Any) -> str:
    """``{"string": "x"}`` / ``{"str": "x"}`` -> ``"x"``; passthrough otherwise."""
    if isinstance(v, dict):
        for k in ("string", "str", "buffer", "content"):
            if k in v:
                return str(v[k])
        return ""
    return "" if v is None else str(v)


def _get(raw: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for k in keys:
        if k in raw and raw[k] not in (None, ""):
            return raw[k]
    return default


@dataclass
class InMsg:
    msg_id: str
    from_wxid: str
    to_wxid: str
    kind: str
    body: str
    is_self: bool
    is_group: bool
    nickname: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def iter_push_messages(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield individual raw message dicts from whatever the push delivered."""
    if isinstance(payload, list):
        yield from (m for m in payload if isinstance(m, dict))
        return
    if not isinstance(payload, dict):
        return
    for key in _MSG_LIST_KEYS:
        v = payload.get(key)
        if isinstance(v, list):
            yield from (m for m in v if isinstance(m, dict))
            return
        if isinstance(v, dict) and any(k in v for k in _SINGLE_MARKERS):
            yield v
            return
    if any(k in payload for k in _SINGLE_MARKERS):
        yield payload  # WeChatPadPro webhook: one flat message object per POST


_REFER_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_REFER_QUOTED = re.compile(r"<refermsg>.*?<content>(.*?)</content>.*?</refermsg>", re.S)


def _flatten_reference(content: str) -> str:
    """Quoted-reply app msg -> ``"<reply>（引用：<quoted>）"`` plain text."""
    title = _REFER_TITLE.search(content or "")
    quoted = _REFER_QUOTED.search(content or "")
    reply = (title.group(1).strip() if title else "").strip()
    q = (quoted.group(1).strip() if quoted else "").strip()
    if reply and q:
        return f"{reply}（引用：{q}）"
    return reply or content or ""


def to_std(raw: dict[str, Any], *, self_wxid: str) -> InMsg | None:
    """Normalise one raw message.  Returns None for kinds this skeleton skips.

    Primary target: WeChatPadPro webhook body (flat, camelCase:
    ``{"msgType": 1, "fromUser": "...", "toUser": "...", "content": "..."}``).
    Also tolerates the PascalCase / ``{"string": ...}``-wrapped shapes other
    pad-protocol distros use.
    """
    try:
        msg_type = int(_get(raw, "msgType", "MsgType", "msg_type", "type", default=0) or 0)
    except (TypeError, ValueError):
        msg_type = 0
    kind = _TYPE_MAP.get(msg_type, "other")

    from_wxid = _unwrap(_get(raw, "fromUser", "FromUserName", "from_wxid", "from"))
    to_wxid = _unwrap(_get(raw, "toUser", "ToUserName", "to_wxid", "to"))
    content = _unwrap(_get(raw, "content", "Content", "PushContent", "msg"))
    msg_id = str(_get(raw, *_MSGID_KEYS, default=""))
    nickname = _unwrap(_get(raw, "nickName", "NickName", "nickname", "senderNickName", default="")) or None

    is_group = from_wxid.endswith("@chatroom") or to_wxid.endswith("@chatroom")

    # in a group, the real sender wxid is prefixed into Content as "wxid:\n..."
    if is_group and ":\n" in content:
        head, _, rest = content.partition(":\n")
        if head and not head.startswith("<"):
            from_wxid, content = head, rest

    if kind == "reference":
        content = _flatten_reference(content)
        kind = "text"

    # skeleton: text only. TODO: handle image/voice (download + STT/vision).
    if kind != "text" or not content.strip():
        return None

    return InMsg(
        msg_id=msg_id or f"{from_wxid}:{hash(content) & 0xffffffff}",
        from_wxid=from_wxid,
        to_wxid=to_wxid,
        kind="text",
        body=content.strip(),
        is_self=bool(self_wxid) and from_wxid == self_wxid,
        is_group=is_group,
        nickname=nickname,
        raw=raw,
    )
