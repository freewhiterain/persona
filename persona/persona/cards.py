"""Character cards: ``characters/<id>/card.toml`` (+ optional ``lore/*.md``).

A card is loaded into a plain dict and mirrored into the ``users`` table as
an ``is_character`` row whose ``meta`` carries the persona fields the
prompt blocks read.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from persona.config import Settings, get_settings
from persona.logging_conf import get_logger
from persona.memory.summarize import ingest_lore_dir
from persona.store.memory import MemoryStore
from persona.store.users import UserStore

logger = get_logger(__name__)

_CARD_FIELDS = ("persona", "speech_style", "longterm_goal", "shortterm_goal", "attitude", "prompt_preset")


def card_dir(character_id: str, settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return s.characters_dir / character_id


def load_card(character_id: str, settings: Settings | None = None) -> dict[str, Any]:
    path = card_dir(character_id, settings) / "card.toml"
    if not path.exists():
        raise FileNotFoundError(f"character card not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    data.setdefault("id", character_id)
    data.setdefault("display_name", data["id"])
    for f in _CARD_FIELDS:
        data.setdefault(f, "")
    data.setdefault("models", {})
    data.setdefault("memory", {})
    return data


def ensure_character(card: dict[str, Any]) -> dict[str, Any]:
    """Upsert the users row for this card; return it merged with card fields."""
    meta = {k: card.get(k, "") for k in _CARD_FIELDS}
    meta["models"] = card.get("models", {})
    user = UserStore().upsert(
        name=card["id"],
        display_name=card["display_name"],
        is_character=True,
        meta=meta,
    )
    return {**user, **meta, "display_name": card["display_name"]}


def seed_character(character_id: str, settings: Settings | None = None) -> dict[str, Any]:
    """Load + register the character and (once) ingest its lore folder."""
    s = settings or get_settings()
    card = load_card(character_id, s)
    row = ensure_character(card)
    if card.get("memory", {}).get("seed_lore", False):
        store = MemoryStore()
        if store.count(row["id"], "character_global") == 0:
            n = ingest_lore_dir(store, card_dir(character_id, s) / "lore", character_id=row["id"])
            logger.info("seeded %d lore rows for %s", n, character_id)
    return row


def character_view(row: dict[str, Any]) -> dict[str, Any]:
    """Shape a users row (+meta) into the dict the prompt blocks expect."""
    meta = row.get("meta", {}) if "meta" in row else row
    return {
        "id": row["id"],
        "name": row["name"],
        "display_name": row["display_name"],
        "persona": meta.get("persona", ""),
        "speech_style": meta.get("speech_style", ""),
        "prompt_preset": meta.get("prompt_preset", "") or None,
        "models": meta.get("models", {}),
    }
