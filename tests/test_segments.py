from __future__ import annotations

from persona.chat.agents.respond import normalize_segments


def test_plain_segments():
    r = {"Segments": [{"type": "text", "content": "在的"}, {"type": "text", "content": "怎么了"}]}
    assert [s["content"] for s in normalize_segments(r)] == ["在的", "怎么了"]


def test_reply_fallback_splits_on_br():
    assert [s["content"] for s in normalize_segments({"Reply": "在的<br>刚忙完"})] == ["在的", "刚忙完"]


def test_leaked_json_object_as_segment_lines():
    """Weak model emitted the JSON of one segment as separate list items."""
    r = {"Segments": ["{", '"type": "text",', '"content": "手上还有新活儿在煮。"', "}"]}
    assert [s["content"] for s in normalize_segments(r)] == ["手上还有新活儿在煮。"]


def test_leaked_json_array_in_reply():
    r = {"Reply": '[{"type":"text","content":"第一句"},{"type":"text","content":"第二句"}]'}
    assert [s["content"] for s in normalize_segments(r)] == ["第一句", "第二句"]


def test_stray_brace_fragment_dropped():
    r = {"Segments": ["}", {"type": "text", "content": "正常内容"}]}
    assert [s["content"] for s in normalize_segments(r)] == ["正常内容"]


def test_empty_falls_back_to_placeholder():
    assert normalize_segments({"Segments": [], "Reply": ""}) == [{"type": "text", "content": "……"}]
