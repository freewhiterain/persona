"""Embedder backends.

* :class:`OpenAIEmbedder` — OpenAI-compatible ``/embeddings`` (works with
  Ollama's ``qwen3-embedding`` etc.)
* :class:`HashEmbedder` — deterministic, offline, no model.  Hashes token
  n-grams into a fixed-width bag-of-words vector.  Not semantic, but keeps
  the whole recall pipeline exercised without a network.

``get_embedder()`` picks one from settings (``effective_embedder`` forces
hash in offline mode).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from persona.config import get_settings
from persona.logging_conf import get_logger

logger = get_logger(__name__)


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


class _Base:
    dim: int = 0

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]  # type: ignore[attr-defined]


class OpenAIEmbedder(_Base):
    def __init__(self, model: str) -> None:
        from persona.core.llm_client import get_llm

        self.model = model
        self._llm = get_llm()
        self.dim = 0  # discovered on first call

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._llm.embed(texts, self.model)
        if vecs and not self.dim:
            self.dim = len(vecs[0])
        return vecs


class HashEmbedder(_Base):
    _tok = re.compile(r"[0-9A-Za-z_]+|[一-鿿]")

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        chars = self._tok.findall(text.lower())
        grams = list(chars)
        grams += ["".join(p) for p in zip(chars, chars[1:])]  # bigrams for CJK
        return grams

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            for tok in self._tokens(text):
                h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "little")
                v[h % self.dim] += 1.0
            n = math.sqrt(float(v.dot(v)))
            if n:
                v /= n
            out.append(v.tolist())
        return out


_singleton: Embedder | None = None


def get_embedder() -> Embedder:
    global _singleton
    if _singleton is not None:
        return _singleton
    s = get_settings()
    if s.effective_embedder == "openai":
        _singleton = OpenAIEmbedder(s.cfg.embedding_model)
        logger.info("embedder: openai (%s)", s.cfg.embedding_model)
    else:
        _singleton = HashEmbedder(s.cfg.embedding_dim)
        logger.info("embedder: hash (dim=%d)", s.cfg.embedding_dim)
    return _singleton


def reset_embedder_cache() -> None:
    global _singleton
    _singleton = None
