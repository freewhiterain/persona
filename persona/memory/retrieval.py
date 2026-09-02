"""Multi-route memory recall.

For each memory store we run up to four routes and merge them by weight:

  1. vector search on the *key* embedding      (weight 0.7)
  2. vector search on the *value* embedding    (weight 0.3)
  3. keyword exact-ish match on *key*          (weight 1.0, split across hits)
  4. keyword exact-ish match on *value*        (weight 1.0, split across hits)

then take the top-N by accumulated weight and format as ``key：value`` lines.
This is luoyun's ``QiaoyunContextRetrieveAgent`` logic, de-duplicated into a
single parametrised function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from persona.memory.embedder import get_embedder
from persona.store.memory import MemoryStore

BAR_MIN = 0.30
BAR_MAX = 1.00


@dataclass
class _Merged:
    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_vector(self, rows: list[dict[str, Any]], weight: float) -> None:
        for r in rows:
            sim = min(r["similarity"], BAR_MAX)
            if sim < BAR_MIN:
                continue
            w = weight * (sim - BAR_MIN) / (BAR_MAX - BAR_MIN)
            self._bump(r, w)

    def add_keyword(self, rows: list[dict[str, Any]], total_weight: float) -> None:
        if not rows:
            return
        w = total_weight / len(rows)
        for r in rows:
            self._bump(r, w)

    def _bump(self, r: dict[str, Any], w: float) -> None:
        slot = self.items.get(r["id"])
        if slot is None:
            self.items[r["id"]] = {"id": r["id"], "key": r["key"], "value": r["value"], "weight": w}
        else:
            slot["weight"] += w

    def top_n(self, n: int, *, photo_prefix: bool = False) -> str:
        ranked = sorted(self.items.values(), key=lambda d: d["weight"], reverse=True)[:n]
        lines = []
        for d in ranked:
            line = f'{d["key"]}：{d["value"]}'.strip()
            if photo_prefix:
                line = f'「照片{d["id"]}」{line}'
            lines.append(line)

        return "\n".join(lines)


def _split_keywords(raw: str) -> list[str]:
    return [p.strip() for p in str(raw).replace("，", ",").split(",") if p.strip()]


def recall_store(
    store: MemoryStore,
    *,
    character_id: str,
    user_id: str | None,
    mtype: str,
    question: str,
    keywords: str,
    top_n: int = 6,
    exclude_ids: set[str] | None = None,
    photo_prefix: bool = False,
) -> str:
    question = (question or "").strip()
    if not question or question == "空":
        return ""

    merged = _Merged()
    emb = get_embedder().embed_one(question)

    merged.add_vector(
        store.vector_search(character_id=character_id, mtype=mtype, query_vec=emb,
                            field="key_emb", user_id=user_id, top_k=8),
        weight=0.7,
    )
    merged.add_vector(
        store.vector_search(character_id=character_id, mtype=mtype, query_vec=emb,
                            field="value_emb", user_id=user_id, top_k=8),
        weight=0.3,
    )
    kws = _split_keywords(keywords)
    if kws:
        merged.add_keyword(
            store.keyword_search(character_id=character_id, mtype=mtype, field="key",
                                 keywords=kws, user_id=user_id, limit=5),
            total_weight=1.0,
        )
        merged.add_keyword(
            store.keyword_search(character_id=character_id, mtype=mtype, field="value",
                                 keywords=kws, user_id=user_id, limit=5),
            total_weight=1.0,
        )

    if exclude_ids:
        for rid in list(merged.items):
            if rid in exclude_ids:
                merged.items.pop(rid)

    return merged.top_n(top_n, photo_prefix=photo_prefix)


def recall(
    query: dict[str, Any],
    *,
    character_id: str,
    user_id: str,
    store: MemoryStore | None = None,
) -> dict[str, str]:
    """query = the QueryRewriteAgent output dict."""
    store = store or MemoryStore()
    g = query.get
    return {
        "character_global": recall_store(
            store, character_id=character_id, user_id=user_id, mtype="character_global",
            question=g("CharacterSettingQueryQuestion", "空"),
            keywords=g("CharacterSettingQueryKeywords", ""),
        ),
        "character_private": recall_store(
            store, character_id=character_id, user_id=user_id, mtype="character_private",
            question=g("CharacterSettingQueryQuestion", "空"),
            keywords=g("CharacterSettingQueryKeywords", ""),
        ),
        "user_profile": recall_store(
            store, character_id=character_id, user_id=user_id, mtype="user_profile",
            question=g("UserProfileQueryQuestion", "空"),
            keywords=g("UserProfileQueryKeywords", ""),
        ),
        "character_knowledge": recall_store(
            store, character_id=character_id, user_id=user_id, mtype="character_knowledge",
            question=g("CharacterKnowledgeQueryQuestion", "空"),
            keywords=g("CharacterKnowledgeQueryKeywords", ""),
        ),
    }
