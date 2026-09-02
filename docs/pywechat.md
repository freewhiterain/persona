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
   automation by default — pyweixin sees the window `class_name` as
   `Qt51514QWindowIcon` and can't do anything. To unlock it:
   1. **Log out** of WeChat
   2. Turn on Windows **讲述人 / Narrator** (`Win+Ctrl+Enter`)
   3. **Log back in** to WeChat
   4. Leave Narrator running **5+ minutes**
   5. (optional) turn Narrator off
   6. verify — the window `class_name` should now be `mmui::MainWindow`:
      ```
      uv run python -c "import win32gui,pythoncom; pythoncom.CoInitialize(); \
        from pywinauto import Desktop; \
        h=win32gui.FindWindow('Qt51514QWindowIcon','微信') or win32gui.FindWindow('Qt51514QWindowIcon','Weixin'); \
        print(Desktop(backend='uia').window(handle=h).class_name())"
      ```
   After a few sessions WeChat "remembers" and you can skip this.
   (Why: the Windows UI Automation API must expose all elements to screen
   readers, so enabling a screen reader forces WeChat to un-hide its tree.)
3. Install the connector deps and vendor `pyweixin` (its PyPI build is
   unusable):
   ```
   uv sync --extra wechat-ui
   # get the source
   git clone https://github.com/Hello-Mr-Crab/pywechat.git
   mkdir vendor
   cp -r pywechat/Mcp/pyweixin_rpa/pyweixin vendor/pyweixin
   # point the venv at ./vendor
   python -c "import sysconfig,pathlib; \
     p=pathlib.Path(sysconfig.get_paths()['purelib'])/'_persona_vendor.pth'; \
     p.write_text(str(pathlib.Path('vendor').resolve()))"
   uv run python -c "from pyweixin import Messages; print('ok')"
   ```
   `vendor/` is gitignored — redo this on a fresh clone of persona.
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
