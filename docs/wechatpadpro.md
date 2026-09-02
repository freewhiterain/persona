# WeChatPadPro connector

Self-hosted WeChat iPad-protocol server → `persona` via
`persona/connectors/wechatpadpro/`. Runner / pipeline / queue are untouched;
this is pure transport.

> Personal-account automation violates WeChat's ToS and carries a real ban
> risk. Use a secondary account.

## About WeChatPadPro

Repo: <https://github.com/WeChatPadPro/WeChatPadPro> (closed-source binary;
this family gets DMCA'd and moves — verify it's live). Verified here against
**v860**.

- Needs **MySQL 8 + Redis 6**. `deploy/docker-compose.yml` bundles both + the
  service. A binary release also exists (`config.json`), then you run MySQL +
  Redis yourself.
- Container listens on **1238** (main API + Swagger UI) and 8080.
- `deploy/.env`: set `ADMIN_KEY`.
- **Windows note:** ports 1238 and 3306 fall in the WinNAT/Hyper-V reserved
  range (`netsh interface ipv4 show excludedportrange protocol=tcp`), so
  `docker compose up` fails to bind them. Remap the *host* side in
  `deploy/docker-compose.yml`, e.g. `"12380:1238"`, drop the `3306` / `6379`
  host mappings (containers reach each other over the compose network). Then
  `base_url = "http://localhost:12380"`.

## Deploy (Docker)

```bash
git clone https://github.com/WeChatPadPro/WeChatPadPro.git
cd WeChatPadPro/deploy
#   edit .env: ADMIN_KEY=<something>
#   (Windows) edit docker-compose.yml host ports as above
docker compose up -d
docker compose ps          # wechatpadpro + mysql + redis healthy
```

Open `http://localhost:<port>/docs` → Swagger UI. Full spec at
`/docs/swagger.json`.

### Log in the account

1. `POST /admin/GenAuthKey1?key=<ADMIN_KEY>` (body `{"Count":1,"Days":365}`) →
   a per-account **authKey**. That's your `WECHATPADPRO_TOKEN`.
2. `POST /login/GetLoginQrCodeNewX?key=<authKey>` → QR; scan with the secondary
   phone. `GET /login/GetLoginStatus?key=<authKey>` to confirm. First login
   drops once within 24h — scan again.
3. Note the account's **wxid** (in the login status payload).

## Configure persona

`.env`:

```
WECHATPADPRO_TOKEN=<authKey>
```

`config.toml` `[wechatpadpro]`:

```toml
enabled   = true
base_url  = "http://localhost:12380"   # your remapped port; or http://wechatpadpro:1238 in-compose
self_wxid = "wxid_your_secondary"
character = "lin"
push_mode = "ws"                        # GET /ws/GetSyncMsg?key= — simplest
# push_mode = "webhook"                 # alternative; also set webhook_secret + register the URL
```

`uv sync --extra wechat`, `uv run persona init` once, then `uv run persona wechat`.

## Confirmed API (v860 `/docs/swagger.json`)

| purpose | call |
| --- | --- |
| auth | every call takes `?key=<authKey>` (query) |
| send text | `POST /message/SendTextMessage` — body `{"MsgItem":[{"ToUserName":"<wxid>","TextContent":"<text>","MsgType":1,"AtWxIDList":[]}]}` |
| receive (ws) | `GET /ws/GetSyncMsg?key=<authKey>` — streams message frames |
| receive (poll) | `POST /message/HttpSyncMsg` — body `{"Count":0}` |
| receive (webhook) | `POST /webhook/Config` — `{Enabled, URL, MessageTypes, Secret, IncludeSelfMessage, RetryCount, Timeout}` |
| voice / image / video in | `POST /message/GetMsgVoice` · `/message/GetMsgBigImg` · `/message/GetMsgVideo` |

Message-type numbers (from the webhook reference client): `1` text · `3`
image · `34` voice · `43` video · `47` sticker · `49` app/link/file ·
`10000` system.

Webhook body shape (reference client): flat camelCase, one object per POST —
`{"msgType":1,"fromUser":"...","toUser":"...","content":"...","msgId":"...","nickName":"..."}`;
signature headers `X-Webhook-Timestamp` + `X-Webhook-Signature` =
`HMAC_SHA256(secret, timestamp + raw_body)` hex.

`adapter.to_std` reads camelCase first and still tolerates PascalCase /
`{"string": …}` shapes. **The exact WS-frame field casing is unverified**
(needs a logged-in account) — the adapter's fallbacks should cover it; adjust
`adapter._get` keys if a real frame differs.

## Not done (skeleton)

- image / voice in & out (media download + STT / TTS / vision)
- group chat (adapter detects `@chatroom` and skips it)
- restart-safe dedup (msg-id dedup is in-memory only)
- login/session health monitoring, auto re-login
- multi-account (one connector process = one character = one WeChat login)
