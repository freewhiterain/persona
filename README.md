# persona

A lightweight virtual-persona chat framework: a multi-agent pipeline that
produces delayed / interruptible replies, a multi-route memory that recalls
and self-updates, and an affinity / proactive-message system.

Architecturally modelled on `luoyun_project`, rewritten from scratch on a
much lighter stack:

| concern | this project |
| --- | --- |
| storage | one SQLite file (WAL), vectors as BLOBs + brute-force cosine |
| LLM | any OpenAI-compatible endpoint (OpenAI / DeepSeek / Doubao / **local Ollama**) |
| embeddings | OpenAI-compatible `/embeddings`, or an offline hash embedder |
| transport | terminal CLI (connector interface left open for IM) |

Voice/image, daily scripts, news learning and "moments" from the original
are intentionally left out for now (schema headroom + extension points kept).

## Quick start (fully local)

```bash
cd persona
uv sync --extra dev
cp .env.example .env          # defaults point at local Ollama
uv run persona init           # create persona.db, seed the example character
uv run persona chat           # talk to her in the terminal
```

Set `PERSONA_FAKE_LLM=1` in `.env` to run with zero network (canned LLM
replies + hash embedder) — used by the test suite and for smoke runs.

See `config.example.toml` for model-role mapping and behaviour knobs.

## Status

Work in progress. See `AGENTS`/commit history for what's wired.
