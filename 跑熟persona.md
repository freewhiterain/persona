# 跑熟 persona（终端版）

前提：Ollama 在跑（`Stheno:latest` / `deepseek-r1:8b` / `qwen3-embedding:4b`）。

## 启动

```bash
cd D:\Desktop\python\c
uv run persona init          # 建库 + 灌角色「林岫」的设定（只需一次）
uv run persona chat          # 开始对话，Ctrl+C 退出
```

一轮回复要 30~60 秒（本地 8B 模型，正常）。回复会分 1~3 条、带打字延迟错峰发出。

## 一轮对话里发生了什么

```
你发一句
  → 问题重写（判断要查哪些资料）
  → 记忆召回（向量 + 关键词，从 5 个库里加权取 top）
  → 生成回复（结合人设/关系/记忆，输出分段消息 + 关系变化 + 未来主动计划）
  → [有概率] deepseek-r1 润色一遍
  → 分段发出（错峰）
  → 事后分析（把新事实写回记忆库，更新关系/态度/印象/反感度）
```

## 看它在学什么

```bash
# 记忆库
uv run python -c "from persona.store.db import get_db; [print(r) for r in get_db().query_all('SELECT mtype,key,substr(value,1,50) FROM memories')]"

# 关系数值
uv run python -c "from persona.store.db import get_db; import json; print(json.loads(get_db().query_one(\"SELECT relationship FROM relations\")['relationship']))"

# 对话历史
uv run python -c "from persona.store.db import get_db; import json; [print(m['body']) for m in json.loads(get_db().query_one('SELECT info FROM conversations')['info'])['chat_history']]"
```

`closeness`/`trustness` 每轮 −5~+5，会随时间衰减；`dislike` 到 100 会拉黑。
聊几轮后 `memories` 里会多出 `character_private` / `user_profile` 之类的行——那是它记住的东西，下次对话会被召回。

## 改角色

- `characters\lin\card.toml`：人设、说话风格、目标、态度
- `characters\lin\lore\*.md`：背景故事、技能（一级标题 = key，正文 = value）
- 改完删库重来：`del persona.db*` 然后 `uv run persona init`
- 新角色：复制 `characters\lin` 文件夹改名，`uv run persona init --character 新名字`，`uv run persona chat --character 新名字`

## 调行为

`config.toml`：
- `[models]` main/fast/refine → 换模型（比如 main 换成更大的模型质量更好）
- `prompt_preset` → `roleplay`（干净）/ `novel`（越狱式，更放得开）
- `[runner] typing_speed` → 分段发送的快慢
- `[relations]` → 衰减间隔、主动消息概率、拉黑阈值

## 重置

```bash
del persona.db persona.db-wal persona.db-shm
uv run persona init
```

## 主动消息（可选）

`persona chat` 里已经在跑后台循环。想快点看到「林岫」主动找话：把 `config.toml`
`[relations] proactive_every_seconds` 调小（如 60）、`proactive_base_chance` 调大（如 0.5），
聊几句后等一会儿。
