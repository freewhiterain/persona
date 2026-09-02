# WeChatPadPro connector

Self-hosted WeChat iPad-protocol server → `persona` via
`persona/connectors/wechatpadpro/`. The runner / pipeline / queue are
untouched; this is pure transport.

> Personal-account automation violates WeChat's ToS and carries a real ban
> risk. Use a secondary account.

## About WeChatPadPro itself

Repo: <https://github.com/WeChatPadPro/WeChatPadPro> (this family of projects
gets DMCA'd and moves — verify the repo is live and read *its* current docs).

- **Needs MySQL 5.7+ and Redis**, either way you run it.
- **Docker Compose** (`deploy/`, edit `.env`, `docker-compose up -d`) bundles
  MySQL + Redis + the service — the least-effort path.
- **Binary** release also exists: extract, edit `setting.json` (DB strings),
  run the MySQL init, run `wechat_service`. No Docker, but you install and run
  MySQL + Redis yourself.
- Default HTTP port `1238`; admin endpoints around `8848`.
- Login: `POST /api/login/qr/newx` → scan QR. **First login drops once within
  24h**, then re-scan for ~3 months of uptime.
- Per-account auth key: `GET /api/login/GenAuthKey2?key=<ADMIN_KEY>&count=1&days=365`
  → that's your `WECHATPADPRO_TOKEN`.
- Inbound = **HTTP webhook**: edit `webhook_config.json` (URL, event types,
  secret); events POST'd with an **HMAC-SHA256** signature. Point its URL at
  `http://<persona-host>:9101/wechat/callback`.

Other distros (`wechat-ipad-protocol`, etc.) differ — some stream over
WebSocket; set `push_mode = "ws"` and `ws_path` for those.

## Wire-up

1. `uv sync --extra wechat`
2. Bring up WeChatPadPro (+ MySQL + Redis). Scan QR. `GenAuthKey2` → token.
3. In `webhook_config.json`: URL `http://<persona-host>:9101/wechat/callback`,
   note the `secret`.
4. `.env`: `WECHATPADPRO_TOKEN=<token>`
5. `config.toml` `[wechatpadpro]`: `enabled = true`, `base_url`, `self_wxid`
   (your account's wxid), `character`, `webhook_secret`.
6. `uv run persona init` once, then `uv run persona wechat`.

## Confirm from the running server's Swagger

The webhook side (default) is wired; verify the **send** side and the
**push envelope**. Every guess is marked `TODO confirm` in code.

| # | what | where | current guess |
| - | --- | --- | --- |
| 1 | **send text** endpoint + payload | `client.py::send_text`, `config send_text_path` | `POST /api/v1/message/sendText`, `{ToUserName, TextContent, AtWxIDList}` |
| 2 | **auth placement**: `?key=` query vs `Authorization` header | `client.py::_post` | `?key=<token>` |
| 3 | **push envelope**: message-list key, field names, `{"string": …}` wrapping, group-sender prefix | `adapter.py` (`_MSG_LIST_KEYS`, `_get`, `_unwrap`, `to_std`) | `AddMsgs[]`, `FromUserName` / `Content` / `MsgType` |
| 4 | **webhook signature**: header name, hex vs base64 | `connector.py::_inbound_webhook` | header `X-Signature`, hex digest |

`adapter.to_std` normalises the common variants and flattens quoted replies;
returns `None` for non-text kinds.

## Identity mapping

- inbound user → `UserStore.get_or_create_external("wechat", wxid, nickname)`
  → row `name = "wechat:<wxid>"`, `meta.external_id = wxid`
- outbound → `deliver()` reads `meta.external_id` to address the send
- character → the `is_character` row for `[wechatpadpro].character`; its id is
  `outbound_from_id`, so this connector only sends that character's messages

## Not done (skeleton)

- image / voice in & out (media download + STT / TTS / vision)
- group chat (adapter detects and skips it)
- restart-safe dedup (msg-id dedup is in-memory only)
- login/session health monitoring, auto re-login
