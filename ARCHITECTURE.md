# Architecture

## Layout

```
persona/
  config.py            merged .env (pydantic-settings) + config.toml (tomllib)
  core/
    agent.py           BaseAgent: generator run(), prehandle/execute/posthandle,
                       whole-run retry, AgentStatus, run_to_resp()
    llm_client.py      OpenAI-compatible wrapper; model-role -> name; <think>
                       stripping; extract_json (+ truncated-JSON repair);
                       FakeLLM for offline mode
    llm_agent.py       LLMAgent: templated prompts, JSON-mode structured output,
                       default_input deep-merge; _make_system/_make_user seams
  store/               SQLite (WAL); every "collection" is a table
    db.py              connection (per-thread), schema, json helpers
    users / conversations / relations / messages   DAOs
    memory.py          memories table: upsert (dedupe on key), vector_search,
                       keyword_search
    vector.py          float32 <-> BLOB, cosine, rank
    locks.py           LockManager: unique-row advisory lock w/ TTL sweep
  memory/
    embedder.py        OpenAIEmbedder | HashEmbedder (offline), get_embedder()
    retrieval.py       recall(): 4 routes per store, weighted merge, top-N
    summarize.py       kv-line ingest, lore/*.md ingest
  chat/                the persona/conversation domain
    cards.py           load card.toml, mirror to users row, seed lore
    context.py         build per-turn ctx; message -> prompt text; CN-time parse
    prompts/           system presets (roleplay/novel), context blocks, tasks
    agents/            query_rewrite, respond (+ proactive), refine, post_analyze
    pipeline.py        ChatPipeline / ProactivePipeline
  connectors/
    base.py            Connector ABC (run_inbound / deliver / run_outbound)
    terminal.py        stdin -> queue, due outbound -> stdout
  runner/
    handler.py         main_handler(): one inbound batch -> replies
    background.py       background_handler(): decay, proactive roll, due-future
    daemon.py          asyncio tick loops over both
```

## A turn (`main_handler`)

```
pending inbound for character
  -> pick oldest sender, get_or_create private conversation
  -> LockManager.acquire("conversation:<id>")            # skip if held
  -> mark that sender's pending inbound = 'handling'
  -> build_context(character, user, conversation, relation)
  -> branch:
       dislike >= blacklist        -> emit "[系统] 拉黑", commit, done
       relationship.status != 空闲  -> mark inbound 'hold', release, done
       else                         -> ChatPipeline(ctx).run()
  -> on AgentStatus.MESSAGE: enqueue each reply segment as outbound with
     expect_ts staggered by typing_speed
  -> if has_pending_inbound() becomes true mid-run: rollback (still commit
     what was said; next tick reprocesses with the new message in history)
  -> commit: append inbound + emitted to chat_history (trim), save
     conversation.info + relation
  -> mark inbound 'handled', release lock
```

`ChatPipeline._execute` (a generator, sub-agents driven via `run_to_resp()`):

```
reset future.proactive_times (inbound turn only)
QueryRewriteAgent            -> ctx["query"]            role=fast
memory.recall(query)         -> ctx["recall"]          (embeds question, 4 routes/store)
RespondAgent                 -> resp{Segments, KnowledgeInvolved,
                                    RelationDelta, FutureResponse}   role=main
   posthandle: clamp closeness/trustness 0..100; probabilistically book
   ctx.future from FutureResponse (damped by proactive_times)
[RefineAgent]                -> rewrite Segments        role=refine
   (chance = 0.12, or 0.5 when KnowledgeInvolved)
yield MESSAGE {segments}     -> handler enqueues them
PostAnalyzeAgent             -> ingest new k:v into memories (character_global
                               /_private/user_profile/knowledge); update
                               relation realname/hobbyname/description/
                               attitude/purpose/dislike                role=fast
```

`ProactivePipeline` = same chain with `ProactiveRespondAgent` (uses the
`planned_action` block instead of the latest inbound), no post-analyze, and
does **not** reset proactive damping.

## Background (`background_handler`, interval-gated in-memory)

- **decay**: every `relations.decay_every_seconds`, closeness/trustness −1 (≥0)
  for every relation of the character
- **proactive roll**: every `relations.proactive_every_seconds`, for each
  eligible relation, `chance = ((closeness+trustness)/200 + 0.5) *
  proactive_base_chance`, damped by prior `proactive_times`; on hit, write a
  random topic into `conversation.info.future`
- **due-future dispatch**: conversations whose `future.timestamp` is within the
  last 30 min run through `ProactivePipeline`; then `future` is cleared and
  `proactive_times` incremented

Busy/idle (`relationship.status`) switching has no driver yet — the field and
the "idle → `requeue_held`" path exist for a future scheduler module.

## Data model (SQLite)

| table | key columns | notes |
| --- | --- | --- |
| `users` | `id`, `name` (unique-ish), `is_character`, `meta` JSON | characters carry card fields in `meta` |
| `conversations` | `id`, `participants` JSON (sorted pair), `info` JSON | `info` = chat_history / input_messages / future / photo_history |
| `relations` | `(user_id, character_id)` unique | `relationship` = description / closeness / trustness / dislike / status |
| `messages` | `direction` in/out, `status`, `expect_ts` | pending→handling→handled / hold / failed |
| `memories` | `(character_id, mtype, key)` unique | `key_emb` / `value_emb` BLOBs; mtype ∈ character_global / character_private / user_profile / character_knowledge / character_photo |
| `locks` | `resource` PK | `owner` token + `expires_ts`; expired rows swept on acquire |

## Extension points

- **new transport**: implement `connectors.base.Connector`, feed the queue
- **daily scripts / news / moments**: add a `jobs/` package driven from
  `background_handler`; `mtype="character_photo"` and `info.photo_history` are
  already reserved
- **multimodal**: `messages.kind` already carries `text|voice|image`;
  `Segments[].type` too — add encode/decode in a connector + tools
- **swap vector store**: replace `store.vector` / `MemoryStore` internals
  (sqlite-vec, chroma) without touching `memory.retrieval` callers
- **prompt style**: `prompts/__init__.py` preset registry (`roleplay`/`novel`),
  selectable globally or per character card
