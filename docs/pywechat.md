# PC WeChat UI-automation connector (pyweixin)

Drives the **real Windows PC WeChat** window via the accessibility tree —
no hook, no protocol server. Free, open-source, actively maintained, works
on **WeChat 4.1.6+**, lowest ban risk of the free options.

Trade-offs: needs an always-on Windows session with WeChat open; ~1–2 s per
action; fragile to WeChat UI redesigns; contacts are addressed by **display
name / 备注**, not wxid.

> Automating a personal account still violates WeChat's ToS. Use a secondary
> account, keep volume low.

## Pieces

```
persona/connectors/pywechat/connector.py
  run_inbound : poll Messages.check_new_messages() every poll_seconds
                -> unread text -> queue.add_inbound
  deliver     : Messages.send_messages_to_friend(friend, [text])
  one threading.Lock serialises every pyweixin call (single WeChat window)
```

`pyweixin` source: <https://github.com/Hello-Mr-Crab/pywechat>

## Setup

1. **A Windows box that stays on**, with PC WeChat **4.1.6+** installed and
   the secondary account logged in.
2. **Make the UI reachable (one-time):** WeChat 4.1+ hides its UI tree from
   automation by default. Turn on Windows **讲述人 / Narrator** (`Win+Ctrl+Enter`)
   *before* logging into WeChat, wait **5+ minutes**, then you may turn
   Narrator off. After a few sessions WeChat "remembers" and you can skip this.
   (Why: the Windows UI Automation API must expose all elements to screen
   readers.)
3. Install the connector deps:
   ```
   uv sync --extra wechat-ui
   ```
   If `pyweixin` from PyPI doesn't work, clone the repo above and add its
   `Mcp/pyweixin_rpa` folder to `PYTHONPATH`.
4. `config.toml` `[pywechat]`:
   ```toml
   enabled   = true
   character = "lin"
   self_name = "你的副号昵称"     # so your own messages aren't treated as inbound
   poll_seconds = 6
   send_delay   = 0.5
   whitelist = []                 # or ["张三"] to only reply to specific people
   ```
5. Run:
   ```
   uv run persona init        # once
   uv run persona wechat-ui
   ```

On start it **primes** the current unread messages (marks them seen, does
*not* reply) so it won't blast a backlog. From then on, new messages from
whitelisted (or any) friends flow through the persona pipeline and replies
are typed back, staggered.

## Identity mapping

- inbound: `friend` (备注/display name) → `UserStore.get_or_create_external("wechat", friend, friend)`
  → row `name = "wechat:<友备注>"`, `meta.external_id = <友备注>`
- outbound: `deliver()` reads `meta.external_id` and calls
  `send_messages_to_friend(friend=<友备注>, ...)`
- If a friend renames themselves / their 备注, they'll be seen as a new user.

## Known limits (skeleton)

- **text only** — image / voice / file / link messages are skipped inbound
  and can't be sent outbound
- **1:1 only** — group messages are detected (sender ≠ chat title) and skipped
- dedup is in-memory (a restart re-primes, so no double-replies, but the
  "seen" history is lost)
- `check_new_messages` opens each unread chat to read it — visibly moves the
  WeChat UI around; don't use that Windows session for anything else
- no login / disconnect monitoring — if WeChat logs out, polling just returns
  nothing until you log back in

## Load / safety notes (from pyweixin docs)

- Too-frequent UI ops make WeChat auto-logout (its own detection). Keep
  `poll_seconds` ≥ 5 and `send_delay` ≥ 0.3; don't run other bots on the same
  account.
- High-volume automation can still trip WeChat risk control.
