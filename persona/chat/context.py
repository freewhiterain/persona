"""Build the per-turn ``ctx`` dict the agents and prompt blocks consume,
plus helpers to render stored messages into prompt text.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from persona.chat.cards import character_view
from persona.store.users import UserStore

_WEEK = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def fmt_ts(ts: int, *, week: bool = False) -> str:
    dt = datetime.fromtimestamp(ts)
    s = dt.strftime("%Y年%m月%d日 %H:%M")
    return f"{s} {_WEEK[dt.weekday()]}" if week else s


_CN_TIME = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})")


def parse_cn_time(text: str) -> int | None:
    """Parse ``xxxx年xx月xx日xx时xx分`` -> epoch seconds, or None."""
    if not text or text.strip() in {"无", ""}:
        return None
    m = _CN_TIME.search(text)
    if not m:
        return None
    try:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        return int(datetime(y, mo, d, h, mi).timestamp())
    except (ValueError, OverflowError):
        return None


def render_message(msg: dict[str, Any], *, users: UserStore, now_ts: int | None = None) -> str:
    now_ts = now_ts or int(time.time())
    when = msg.get("create_ts") or msg.get("expect_ts") or now_ts
    if msg["direction"] == "out" and when > now_ts:
        return ""  # not sent yet
    talker = users.get(msg["from_id"])
    name = talker["display_name"] if talker else msg["from_id"]
    kind_cn = {"text": "文本", "voice": "语音", "image": "图片"}.get(msg["kind"], "文本")
    return f"（{fmt_ts(when)} {name}发来了{kind_cn}消息）{msg['body']}"


def render_messages(msgs: list[dict[str, Any]], *, users: UserStore | None = None, now_ts: int | None = None) -> str:
    users = users or UserStore()
    lines = [render_message(m, users=users, now_ts=now_ts) for m in msgs]
    return "\n".join(x for x in lines if x)


def build_context(
    *,
    character_row: dict[str, Any],
    user_row: dict[str, Any],
    conversation: dict[str, Any],
    relation: dict[str, Any],
    now_ts: int | None = None,
) -> dict[str, Any]:
    now_ts = now_ts or int(time.time())
    users = UserStore()
    info = conversation["info"]
    character = character_view(character_row)
    user = {"id": user_row["id"], "name": user_row["name"], "display_name": user_row["display_name"]}

    return {
        "now_ts": now_ts,
        "now_str": fmt_ts(now_ts, week=True),
        "character": character,
        "user": user,
        "character_name": character["display_name"],
        "user_name": user["display_name"],
        "conversation": conversation,
        "relation": relation,
        "history_str": render_messages(info.get("chat_history", []), users=users, now_ts=now_ts),
        "latest_str": render_messages(info.get("input_messages", []), users=users, now_ts=now_ts),
        # filled in by the pipeline as it runs:
        "query": {},
        "recall": {"character_global": "", "character_private": "", "user_profile": "", "character_knowledge": ""},
        "reply_segments_str": "",
    }
