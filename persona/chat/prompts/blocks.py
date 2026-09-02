"""Context blocks for the user prompt.

Each function takes the turn ``ctx`` dict (built by
:mod:`persona.chat.context`) and returns a ``### heading`` section as a
plain string — explicit f-strings, so a missing field is an obvious
``KeyError`` at the call site rather than a cryptic ``str.format`` crash.
"""

from __future__ import annotations

from typing import Any, Callable

Ctx = dict[str, Any]


def b_time(ctx: Ctx) -> str:
    return f"### 当前时间（24 小时制）\n{ctx['now_str']}"


def b_character(ctx: Ctx) -> str:
    c = ctx["character"]
    return (
        f"### 你扮演的角色：{c['display_name']}\n"
        f"一句话人设：{c.get('persona', '')}\n"
        f"说话风格：{c.get('speech_style', '')}"
    )


def b_character_profile(ctx: Ctx) -> str:
    r = ctx["recall"]
    body = "\n".join(x for x in (r.get("character_global", ""), r.get("character_private", "")) if x)
    return f"### {ctx['character']['display_name']}的人物资料\n{body or '（暂无）'}"


def b_user_profile(ctx: Ctx) -> str:
    return f"### {ctx['user']['display_name']}的资料\n{ctx['recall'].get('user_profile', '') or '（暂无）'}"


def b_knowledge(ctx: Ctx) -> str:
    return f"### {ctx['character']['display_name']}的知识与技能\n{ctx['recall'].get('character_knowledge', '') or '（暂无）'}"


def b_status(ctx: Ctx) -> str:
    rel = ctx["relation"]["relationship"]
    ci = ctx["relation"]["character_info"]
    return (
        f"### {ctx['character']['display_name']}的当前状态\n"
        f"忙闲：{rel.get('status', '空闲')}\n"
        f"当前态度：{ci.get('attitude', '')}"
    )


def b_goal(ctx: Ctx) -> str:
    ci = ctx["relation"]["character_info"]
    return (
        f"### {ctx['character']['display_name']}的目标\n"
        f"长期：{ci.get('longterm_purpose', '')}\n"
        f"短期：{ci.get('shortterm_purpose', '')}"
    )


def b_relation(ctx: Ctx) -> str:
    r = ctx["relation"]["relationship"]
    ui = ctx["relation"]["user_info"]
    return (
        f"### 你与{ctx['user']['display_name']}的关系\n"
        f"关系描述：{r.get('description', '')}\n"
        f"亲密度：{r.get('closeness', 0)}  信任度：{r.get('trustness', 0)}  反感度：{r.get('dislike', 0)}\n"
        f"已知对方真名：{ui.get('realname') or '未知'}\n"
        f"你对对方的昵称：{ui.get('hobbyname') or '无'}\n"
        f"你对对方的印象：{ui.get('description', '')}"
    )


def b_history(ctx: Ctx) -> str:
    return f"### 历史对话\n{ctx.get('history_str', '') or '（无）'}"


def b_latest(ctx: Ctx) -> str:
    return f"### {ctx['user']['display_name']}的最新消息\n{ctx.get('latest_str', '') or '（空）'}"


def b_latest_both(ctx: Ctx) -> str:
    return (
        f"### {ctx['user']['display_name']}的最新消息\n{ctx.get('latest_str', '') or '（空）'}\n\n"
        f"### {ctx['character']['display_name']}的最新回复\n{ctx.get('reply_segments_str', '') or '（空）'}"
    )


def b_draft_reply(ctx: Ctx) -> str:
    return f"### {ctx['character']['display_name']}的初步回复\n{ctx.get('reply_segments_str', '')}"


def b_planned_action(ctx: Ctx) -> str:
    fut = ctx["conversation"]["info"].get("future") or {}
    return f"### 你之前规划的主动行动\n{fut.get('action', '')}"


_REGISTRY: dict[str, Callable[[Ctx], str]] = {
    "time": b_time,
    "character": b_character,
    "character_profile": b_character_profile,
    "user_profile": b_user_profile,
    "knowledge": b_knowledge,
    "status": b_status,
    "goal": b_goal,
    "relation": b_relation,
    "history": b_history,
    "latest": b_latest,
    "latest_both": b_latest_both,
    "draft_reply": b_draft_reply,
    "planned_action": b_planned_action,
}


def build(ctx: Ctx, keys: list[str]) -> str:
    return "\n\n".join(_REGISTRY[k](ctx) for k in keys)
