"""Helpers to turn model output / lore files into memory rows."""

from __future__ import annotations

import re
from pathlib import Path

from persona.store.memory import MemoryStore

_SEP = re.compile(r"<br>|<换行>|\n")
_KV = re.compile(r"[:：]")


def ingest_kv_lines(
    store: MemoryStore,
    text: str,
    *,
    character_id: str,
    mtype: str,
    user_id: str | None = None,
) -> list[str]:
    """Parse ``key：value`` lines (one per row) and upsert them.

    Returns the list of memory ids written.  ``无`` / blank input is a no-op.
    """
    if not text or text.strip() in {"无", ""}:
        return []
    ids: list[str] = []
    for chunk in _SEP.split(text):
        chunk = chunk.strip().lstrip("-* ").strip()
        if not chunk or chunk == "无":
            continue
        parts = _KV.split(chunk, maxsplit=1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        if not key or not value:
            continue
        try:
            ids.append(
                store.upsert(
                    character_id=character_id, mtype=mtype, key=key, value=value, user_id=user_id
                )
            )
        except ValueError:
            continue
    return ids


def ingest_lore_dir(store: MemoryStore, lore_dir: Path, *, character_id: str) -> int:
    """Each ``## Heading`` in every ``*.md`` becomes a character_global row
    (heading -> key, following text -> value)."""
    if not lore_dir.is_dir():
        return 0
    written = 0
    for md in sorted(lore_dir.glob("*.md")):
        section_key: str | None = None
        buf: list[str] = []

        def flush() -> None:
            nonlocal written, section_key, buf
            if section_key and buf:
                body = "\n".join(buf).strip()
                if body:
                    store.upsert(
                        character_id=character_id,
                        mtype="character_global",
                        key=section_key,
                        value=body,
                    )
                    written += 1
            buf = []

        for line in md.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^#{1,3}\s+(.*)", line)
            if m:
                flush()
                section_key = m.group(1).strip()
            else:
                buf.append(line)
        flush()
    return written
