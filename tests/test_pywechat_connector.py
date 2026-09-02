from __future__ import annotations

import pytest


def test_module_imports_without_pyweixin():
    """The connector must import even though pyweixin isn't installed."""
    from persona.connectors.pywechat import PyWeChatConnector

    assert PyWeChatConnector.name == "pywechat"


def test_config_section_loads(db):
    from persona.config import get_settings

    pw = get_settings().cfg.pywechat
    assert pw.enabled is False
    assert pw.character == "lin"
    assert pw.poll_seconds >= 5
    assert pw.whitelist == []


def test_ensure_behaviour(db):
    """Without pyweixin -> a helpful RuntimeError; with it -> loads cleanly."""
    from persona.connectors.pywechat.connector import PyWeChatConnector

    c = PyWeChatConnector(character_id="cid")
    try:
        import pyweixin  # noqa: F401
    except Exception:
        with pytest.raises(RuntimeError, match="pyweixin"):
            c._ensure()
    else:
        c._ensure()
        assert c._Messages is not None


def test_dedup_key_and_remember(db):
    from persona.connectors.pywechat.connector import PyWeChatConnector

    c = PyWeChatConnector(character_id="cid")
    k = c._key("张三", {"消息发送时间": "2026年9月2日 10:00", "消息内容": "在吗"})
    assert k not in c._seen_set
    c._remember(k)
    assert k in c._seen_set
