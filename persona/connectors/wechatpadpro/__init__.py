"""WeChatPadPro connector (self-hosted WeChat protocol server, Docker).

Skeleton: the standard-message plumbing is done; the WeChatPadPro-specific
bits (exact endpoint paths, auth placement, push envelope shape) are marked
``TODO confirm`` — fill them from your deployment's Swagger.  See
docs/wechatpadpro.md.

Requires the ``wechat`` extra:  uv sync --extra wechat
"""

from persona.connectors.wechatpadpro.connector import WeChatPadProConnector

__all__ = ["WeChatPadProConnector"]
