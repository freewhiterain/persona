"""Vector (de)serialisation + brute-force cosine search.

Small data volumes (a persona's memory is hundreds, not millions, of rows),
so we keep it dead simple: float32 bytes in a BLOB column, cosine in numpy.
Swap :class:`VectorStore` for sqlite-vec / chroma later without touching
callers.
"""

from __future__ import annotations

import numpy as np


def to_blob(vec: list[float] | np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 0.0  # different embedder / model — not comparable
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def rank(query: np.ndarray, rows: list[tuple[str, np.ndarray]], top_k: int) -> list[tuple[str, float]]:
    """rows: (id, embedding) -> [(id, similarity)] sorted desc, length <= top_k.

    Rows whose embedding dimension differs from ``query`` (a DB seeded with a
    different embedder) are scored 0 and effectively dropped.
    """
    scored = [
        (rid, cosine(query, emb))
        for rid, emb in rows
        if emb is not None and emb.shape == query.shape
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top_k]
