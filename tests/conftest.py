from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _reset_all() -> None:
    from persona.config import reset_settings_cache
    from persona.core.llm_client import reset_llm_cache
    from persona.memory.embedder import reset_embedder_cache
    from persona.store.db import reset_db_cache

    reset_settings_cache()
    reset_db_cache()
    reset_llm_cache()
    reset_embedder_cache()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Each test gets a fresh temp DB, offline LLM, real project root."""
    monkeypatch.setenv("PERSONA_FAKE_LLM", "1")
    monkeypatch.setenv("PERSONA_ROOT", str(PROJECT_ROOT))
    monkeypatch.setenv("PERSONA_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("PERSONA_LOG_LEVEL", "WARNING")
    _reset_all()
    yield
    _reset_all()


@pytest.fixture
def db():
    from persona.store.db import get_db

    d = get_db()
    d.init_schema()
    return d


@pytest.fixture
def seeded(db):
    """Return (character_row, user_row) with 'lin' seeded from characters/lin."""
    from persona.persona.cards import seed_character
    from persona.store.users import UserStore

    seed_character("lin")
    users = UserStore()
    lin = users.get_by_name("lin")
    me = users.upsert(name="我", display_name="我")
    return lin, me
