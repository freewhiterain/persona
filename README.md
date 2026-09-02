# persona

A lightweight virtual-persona chat framework. A multi-agent pipeline turns
each inbound message into in-character replies, with:

- **delayed / interruptible replies** — multi-segment output staggered by
  "typing speed"; a new message mid-reply rolls the turn back and re-answers
  with full context ("many-to-one")
- **self-updating memory** — multi-route recall (vector on key + value,
  keyword on key + value, weighted-merged) before each reply; a post-analysis
  pass distils new facts back into the store
- **affinity / emotion** — closeness / trustness / dislike drift per turn and
  decay over time; too much dislike blacklists; "busy" status holds messages
- **proactive messages** — affinity-weighted chance to open a new topic later

Modelled on `luoyun_project`, rewritten from scratch on a lighter stack.

| concern | this project | luoyun |
| --- | --- | --- |
| structured store | one **SQLite** file (WAL) | MongoDB service |
| vectors | `float32` BLOB + numpy brute-force cosine | Mongo + Python cosine |
| LLM | any **OpenAI-compatible** endpoint | Doubao / Volc SDK |
| embeddings | OpenAI-compatible `/embeddings`, or offline hash | Aliyun DashScope |
| transport | terminal CLI; WeChat via protocol server ([docs](docs/wechatpadpro.md)) or PC-UI automation ([docs](docs/pywechat.md)) | E-cloud WeChat hook |
| dropped for now | voice/image, daily scripts, news, moments | — |

## Quick start

```bash
cd persona
uv sync --extra dev
cp .env.example .env          # defaults point at local Ollama
cp config.example.toml config.toml
uv run persona init           # create persona.db, seed the example character "lin"
uv run persona chat           # talk to her in the terminal (Ctrl+C to quit)
```

**Fully offline** (no Ollama, no keys): set `PERSONA_FAKE_LLM=1` in `.env`
(canned LLM replies + hash embedder). This is also what the test suite uses.

```bash
uv run pytest          # 20 tests, no network
```

## Configuration

`.env` — endpoints & secrets:

| var | default | meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | `ollama` / `http://localhost:11434/v1` | chat endpoint |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` | unset → reuse `OPENAI_*` | embeddings endpoint |
| `PERSONA_FAKE_LLM` | `0` | `1` = offline stubs |
| `PERSONA_DB_PATH` | unset | override `config.toml` db path |

`config.toml` — structural knobs (see `config.example.toml`): `prompt_preset`
(`roleplay` \| `novel`), `embedder` (`openai` \| `hash`), `embedding_model`,
`structured_mode`, `[models]` main/fast/refine → model names, `[runner]`
timing, `[relations]` decay / proactive / blacklist.

Local Ollama mapping used by the examples: `main`/`fast` = `Stheno:latest`,
`refine` = `deepseek-r1:8b`, embeddings = `qwen3-embedding:4b`.

## Characters

`characters/<id>/card.toml` + optional `characters/<id>/lore/*.md`
(each `#`/`##` heading becomes a seeded `character_global` memory row).
See `characters/lin/` for the shape. New character: copy the folder, edit
`card.toml`, `uv run persona init --character <id>`.

## CLI

| command | what |
| --- | --- |
| `persona init [--character lin]` | create DB, seed a character + its lore |
| `persona chat [--character lin] [--user 我]` | terminal REPL; daemon runs in-process |
| `persona run [--character lin]` | daemon only (for an external connector) |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md).
