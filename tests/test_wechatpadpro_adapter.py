from __future__ import annotations

from persona.connectors.wechatpadpro.adapter import iter_push_messages, to_std


def _msg(**over):
    base = {
        "MsgId": "1001",
        "MsgType": 1,
        "FromUserName": {"string": "wxid_alice"},
        "ToUserName": {"string": "wxid_bot"},
        "Content": {"string": "在吗"},
        "NickName": "Alice",
    }
    base.update(over)
    return base


def test_to_std_basic_text():
    m = to_std(_msg(), self_wxid="wxid_bot")
    assert m is not None
    assert (m.from_wxid, m.to_wxid, m.body, m.kind) == ("wxid_alice", "wxid_bot", "在吗", "text")
    assert not m.is_self and not m.is_group
    assert m.nickname == "Alice"


def test_to_std_drops_own_and_group_and_nontext():
    assert to_std(_msg(FromUserName="wxid_bot"), self_wxid="wxid_bot").is_self is True
    grp = to_std(_msg(FromUserName="12345@chatroom", Content={"string": "wxid_x:\nhi"}),
                 self_wxid="wxid_bot")
    assert grp.is_group is True and grp.from_wxid == "wxid_x" and grp.body == "hi"
    assert to_std(_msg(MsgType=3, Content={"string": ""}), self_wxid="wxid_bot") is None


def test_to_std_flattens_quoted_reply():
    xml = "<msg><appmsg><title>说得对</title><refermsg><content>原话在此</content></refermsg></appmsg></msg>"
    m = to_std(_msg(MsgType=49, Content={"string": xml}), self_wxid="wxid_bot")
    assert m is not None and m.kind == "text"
    assert "说得对" in m.body and "原话在此" in m.body


def test_iter_push_messages_shapes():
    assert list(iter_push_messages({"AddMsgs": [_msg(), _msg(MsgId="2")]})) != []
    assert list(iter_push_messages(_msg())) == [_msg()]
    assert list(iter_push_messages([_msg()])) == [_msg()]
    assert list(iter_push_messages({"nope": 1})) == []


def test_get_or_create_external_roundtrip(db):
    from persona.store.users import UserStore

    us = UserStore()
    a = us.get_or_create_external("wechat", "wxid_alice", "Alice")
    b = us.get_or_create_external("wechat", "wxid_alice", "Alice")
    assert a["id"] == b["id"]
    assert a["name"] == "wechat:wxid_alice"
    assert a["meta"]["external_id"] == "wxid_alice"
