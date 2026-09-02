from __future__ import annotations

from persona.memory.retrieval import recall, recall_store
from persona.memory.summarize import ingest_kv_lines
from persona.store.memory import MemoryStore


def test_upsert_dedupes_on_key(db):
    store = MemoryStore()
    a = store.upsert(character_id="c", mtype="character_global", key="爱好-登山", value="喜欢爬周边的山")
    b = store.upsert(character_id="c", mtype="character_global", key="爱好-登山", value="尤其是十里琅珰")
    assert a == b
    assert store.count("c", "character_global") == 1
    assert "十里琅珰" in store.get(a)["value"]


def test_recall_ranks_relevant_row_first(db):
    store = MemoryStore()
    store.upsert(character_id="c", mtype="character_global", key="职业", value="在出版社做文学编辑")
    store.upsert(character_id="c", mtype="character_global", key="宠物", value="养了一只叫校样的橘猫")
    store.upsert(character_id="c", mtype="character_global", key="运动", value="周末去爬山")

    out = recall_store(
        store, character_id="c", user_id="u", mtype="character_global",
        question="她的工作是什么", keywords="编辑,出版,工作",
    )
    assert out.splitlines()[0].startswith("职业：")


def test_recall_survives_embedder_dim_mismatch(db):
    """A row embedded by a different embedder (wrong dim) must not crash recall."""
    import numpy as np

    from persona.store.vector import to_blob

    store = MemoryStore()
    mid = store.upsert(character_id="c", mtype="character_global", key="职业", value="文学编辑")
    # clobber the stored vectors with a wrong-dimension embedding
    bad = to_blob(np.ones(2560, dtype="float32"))
    store.db.execute("UPDATE memories SET key_emb=?, value_emb=? WHERE id=?", (bad, bad, mid))

    out = recall_store(
        store, character_id="c", user_id="u", mtype="character_global",
        question="工作", keywords="编辑",
    )
    # keyword route still matches; no exception
    assert "文学编辑" in out


def test_recall_returns_empty_for_blank_query(db):
    out = recall_store(
        MemoryStore(), character_id="c", user_id="u", mtype="character_global",
        question="空", keywords="空",
    )
    assert out == ""


def test_user_scoped_memory_requires_user_id(db):
    store = MemoryStore()
    try:
        store.upsert(character_id="c", mtype="user_profile", key="k", value="v")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for user-scoped mtype without user_id")


def test_ingest_kv_lines(db):
    store = MemoryStore()
    ids = ingest_kv_lines(
        store,
        "工作-单位：在杭州一家出版社<br>宠物-猫：橘猫校样<br>无",
        character_id="c", mtype="character_global",
    )
    assert len(ids) == 2
    assert store.count("c", "character_global") == 2


def test_recall_orchestrator_shape(db):
    store = MemoryStore()
    store.upsert(character_id="c", mtype="character_global", key="职业", value="文学编辑")
    q = {
        "CharacterSettingQueryQuestion": "职业",
        "CharacterSettingQueryKeywords": "编辑",
        "UserProfileQueryQuestion": "空",
        "UserProfileQueryKeywords": "空",
        "CharacterKnowledgeQueryQuestion": "空",
        "CharacterKnowledgeQueryKeywords": "空",
    }
    out = recall(q, character_id="c", user_id="u", store=store)
    assert set(out) == {"character_global", "character_private", "user_profile", "character_knowledge"}
    assert "文学编辑" in out["character_global"]
    assert out["user_profile"] == ""
