# WeChatPadPro connector

Self-hosted WeChat iPad-protocol server → `persona` via
`persona/connectors/wechatpadpro/`. The runner / pipeline / queue are
untouched; this is pure transport.

> Personal-account automation violates WeChat's ToS and carries a real ban
> risk. Use a secondary account.

## About WeChatPadPro

Repo: <https://github.com/WeChatPadPro/WeChatPadPro> (this family gets DMCA'd
and moves — verify it's live and read *its* current docs). Closed-source
binary distribution.

- **Needs MySQL 8 + Redis 6.** Its `deploy/docker-compose.yml` bundles both +
  the service — the easy path. A binary release (`wechatpadpro.exe` /
  `./wechatpadpro`, edit `config.json`) exists too, but then you run MySQL +
  Redis yourself.
- Ports: **1238** main API, 8080 secondary, **8848** admin.
- `deploy/.env`: set `ADMIN_KEY` (default `changeme`), MySQL/Redis creds.
- Login: `POST /api/login/qr/newx` → scan QR. First login drops once within
  24h, then re-scan for ~3 months.
- Per-account key: `GET http://<host>:8848/login/GenAuthKey2?key=<ADMIN_KEY>&count=1&days=365`
  → that string is your `WECHATPADPRO_TOKEN`; API calls take it as `?key=<token>`.

## Deploy (Docker)

```bash
git clone https://github.com/WeChatPadPro/WeChatPadPro.git
cd WeChatPadPro/deploy
#   edit .env: ADMIN_KEY=<something>, (optionally MySQL/Redis passwords)
docker compose up -d
docker compose ps          # wechatpadpro + mysql + redis all healthy
```

Then open `http://localhost:1238` for the QR / API console, log in the
secondary account, and `GenAuthKey2` for the token.

`docs/docker-compose.example.yml` adds a `persona` service next to it.

## Configure persona

Point WeChatPadPro's webhook at persona — edit its `webhook_config.json`
(or `POST /v1/webhook/Config`):

```json
{
  "enabled": true,
  "url": "http://<persona-host>:9101/webhook",
  "events": ["message"],
  "retry_count": 3,
  "retry_interval": 5,
  "secret_key": "<pick-a-secret>"
}
```

`.env`:

```
WECHATPADPRO_TOKEN=<GenAuthKey2 output>
```

`config.toml` `[wechatpadpro]`:

```toml
enabled = true
base_url = "http://localhost:1238"      # http://wechatpadpro:1238 if persona is in the same compose
self_wxid = "wxid_your_secondary"
webhook_secret = "<the same secret>"
character = "lin"
```

`uv sync --extra wechat`, `uv run persona init` once, then `uv run persona wechat`.

## Confirmed contract (from the official webhook reference client)

Inbound webhook — **one flat camelCase JSON object per POST**:

```json
{ "msgType": 1, "fromUser": "wxid_x", "toUser": "wxid_y", "content": "...", "msgId": "...", "nickName": "..." }
```

- signature: headers `X-Webhook-Timestamp` + `X-Webhook-Signature`,
  `HMAC_SHA256(secret_key, timestamp_str + raw_body)` as lowercase hex
- msg types: `1` text · `3` image · `34` voice · `43` video · `47` sticker ·
  `49` app/link/file · `10000` system

`adapter.to_std` reads these (and still tolerates the PascalCase /
`{"string": …}` shapes other distros use). Non-text kinds → `None` (skeleton).

## Still to confirm from the running Swagger (`/swagger` or `/doc`)

Only the **send** side. `POST /api/v1/message/sendFile` is documented with
`{"toUserName": ...}`; the text endpoint is a guess modelled on it:

| where | current guess |
| --- | --- |
| `config send_text_path` | `POST /api/v1/message/sendText` |
| `client.py::send_text` payload | `{"toUserName": <wxid>, "content": <text>, "atWxIDList": []}` |

Fix those two lines once you see the real spec; everything else is wired.

## Identity mapping

- inbound user → `UserStore.get_or_create_external("wechat", fromUser, nickName)`
  → row `name = "wechat:<wxid>"`, `meta.external_id = <wxid>`
- outbound → `deliver()` reads `meta.external_id` to address the send
- character → the `is_character` row for `[wechatpadpro].character`; its id is
  `outbound_from_id`, so this connector only sends that character's messages

## Not done (skeleton)

- image / voice in & out (media download + STT / TTS / vision)
- group chat (adapter detects `@chatroom` and skips it)
- restart-safe dedup (msg-id dedup is in-memory only)
- login/session health monitoring, auto re-login
- multi-account (one connector process = one character = one WeChat login)
