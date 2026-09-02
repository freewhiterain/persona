# WeChatPadPro connector

Self-hosted WeChat iPad-protocol server in Docker → `persona` via
`persona/connectors/wechatpadpro/`. The runner / pipeline / queue are
untouched; this is pure transport.

> Personal-account automation violates WeChat's ToS and carries a real ban
> risk. Use a secondary account. Self-hosting means you also maintain the
> container and its login session.

## Pieces

```
persona/connectors/wechatpadpro/
  client.py      HTTP send client (aiohttp, lazy import)
  adapter.py     push envelope -> standard InMsg (+ self/group/reference handling)
  connector.py   WeChatPadProConnector: run_inbound (ws | webhook) + deliver
```

`persona/connectors/base.py::Connector.run_outbound()` already polls
`due_outbound(from_id=character_id)` and calls `deliver()` — you only
implement `deliver()`.

## Wire-up

1. `uv sync --extra wechat`
2. Run WeChatPadPro (see `docker-compose.example.yml`), scan the QR to log in,
   note the **token** and the account's **wxid**.
3. `.env`: `WECHATPADPRO_TOKEN=...`
4. `config.toml` `[wechatpadpro]`: `enabled = true`, `base_url`, `self_wxid`,
   `character`, `push_mode`.
5. `uv run persona init` (once), then `uv run persona wechat`.

## The 4 things to confirm from your build's Swagger

The skeleton guesses these; every one is marked `TODO confirm` in code.

| # | what | where to fix | current guess |
| - | --- | --- | --- |
| 1 | **push mechanism**: WebSocket sync-stream vs HTTP callback | `config [wechatpadpro].push_mode` + `ws_path` / `webhook_path` | `ws` at `/ws/GetSyncMsg` |
| 2 | **auth placement**: `?key=<token>` query vs `Authorization` header | `client.py::_post` (and `connector.py` ws `params`) | query `?key=` |
| 3 | **send payload shape** for text | `client.py::send_text` | `{"ToUserName", "TextContent", "AtWxIDList"}` |
| 4 | **push envelope**: message-list key, field names, `{"string": ...}` wrapping, group-sender prefix | `adapter.py` (`_MSG_LIST_KEYS`, `_get`, `_unwrap`, `to_std`) | `AddMsgs[]`, `FromUserName`/`Content`/`MsgType` |

`adapter.to_std` already normalises the common variants and flattens quoted
replies; it returns `None` for non-text kinds (image/voice) — those need
download + STT/vision, deferred.

## Identity mapping

- inbound user → `UserStore.get_or_create_external("wechat", wxid, nickname)`
  → row `name = "wechat:<wxid>"`, `meta.external_id = "<wxid>"`
- outbound → `deliver()` reads `meta.external_id` back to address the send
- character → the `is_character` row for `[wechatpadpro].character`; its id is
  `outbound_from_id`, so this connector only sends that character's messages

## Not done (skeleton)

- image / voice in & out (need media download + STT / TTS / vision)
- group chat (adapter detects and skips it)
- restart-safe dedup (msg-id dedup is in-memory only)
- login/health monitoring, re-login on session drop
