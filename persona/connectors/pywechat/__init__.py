"""PyWeChat connector — drives the real PC WeChat window (UI automation).

Backed by ``pyweixin`` (github.com/Hello-Mr-Crab/pywechat): no hook, no
protocol server; it walks WeChat 4.1.6+'s accessibility tree to read unread
messages and type replies.  Windows-only, needs the WeChat window reachable.
See docs/pywechat.md.
"""

from persona.connectors.pywechat.connector import PyWeChatConnector

__all__ = ["PyWeChatConnector"]
