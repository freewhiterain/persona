"""Configuration loading.

Two layers, merged into one :class:`Settings`:

* ``.env``            -> endpoints & secrets (via ``pydantic-settings``)
* ``config.toml``     -> structural knobs (optional; falls back to defaults)

Access the singleton with :func:`get_settings`.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# --------------------------------------------------------------------------- #
# .env layer
# --------------------------------------------------------------------------- #
class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = "ollama"
    openai_base_url: str = "http://localhost:11434/v1"
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    persona_fake_llm: bool = False
    persona_log_level: str = "INFO"
    persona_db_path: str | None = None   # overrides config.toml db_path (tests / one-offs)
    wechatpadpro_token: str | None = None  # overrides config.toml [wechatpadpro].token

    @property
    def emb_key(self) -> str:
        return self.embedding_api_key or self.openai_api_key

    @property
    def emb_url(self) -> str:
        return self.embedding_base_url or self.openai_base_url


# --------------------------------------------------------------------------- #
# config.toml layer
# --------------------------------------------------------------------------- #
class ModelRoles(BaseModel):
    main: str = "Stheno:latest"
    fast: str = "Stheno:latest"
    refine: str = "deepseek-r1:8b"

    def resolve(self, role: str) -> str:
        return getattr(self, role, self.main)


class RunnerConfig(BaseModel):
    tick_seconds: float = 1.0
    typing_speed: float = 2.5
    max_history: int = 50
    max_handle_age: int = 43_200


class RelationsConfig(BaseModel):
    decay_every_seconds: int = 30_240
    proactive_every_seconds: int = 5_338
    proactive_base_chance: float = 0.03
    dislike_analyze_bonus: int = -5
    blacklist_dislike: int = 100


class WeChatPadProConfig(BaseModel):
    """Self-hosted WeChatPadPro (Docker) protocol server.  See
    docs/wechatpadpro.md — the 4 fields you must confirm from its Swagger."""

    enabled: bool = False
    character: str = "lin"            # which character card this WeChat account plays
    base_url: str = "http://localhost:8080"
    token: str = ""                  # or set WECHATPADPRO_TOKEN in .env
    self_wxid: str = ""             # logged-in account's wxid (to drop own messages)

    push_mode: str = "ws"           # "ws" (long-poll sync) | "webhook" (HTTP callback)
    ws_path: str = "/ws/GetSyncMsg"  # TODO confirm
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 9101
    webhook_path: str = "/wechat/callback"

    # send endpoints (TODO confirm names against your build's Swagger)
    send_text_path: str = "/message/SendTextMessage"
    send_image_path: str = "/message/SendImageMessage"
    send_voice_path: str = "/message/SendVoiceMessage"

    reconnect_seconds: float = 3.0
    dedup_window: int = 512          # remember this many recent msg ids


class TomlConfig(BaseModel):
    db_path: str = "persona.db"
    prompt_preset: str = "roleplay"
    embedder: str = "hash"            # "openai" | "hash"
    embedding_model: str = "qwen3-embedding:4b"
    embedding_dim: int = 256          # hash embedder only
    structured_mode: str = "json"     # "json" | "tool"
    models: ModelRoles = Field(default_factory=ModelRoles)
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    relations: RelationsConfig = Field(default_factory=RelationsConfig)
    wechatpadpro: WeChatPadProConfig = Field(default_factory=WeChatPadProConfig)


# --------------------------------------------------------------------------- #
# merged
# --------------------------------------------------------------------------- #
class Settings(BaseModel):
    env: EnvSettings
    cfg: TomlConfig
    project_root: Path

    # convenience passthroughs -------------------------------------------------
    @property
    def fake_llm(self) -> bool:
        return self.env.persona_fake_llm

    @property
    def db_path(self) -> Path:
        p = Path(self.env.persona_db_path or self.cfg.db_path)
        return p if p.is_absolute() else self.project_root / p

    @property
    def characters_dir(self) -> Path:
        return self.project_root / "characters"

    @property
    def effective_embedder(self) -> str:
        # offline mode can't reach an embeddings endpoint
        return "hash" if self.fake_llm else self.cfg.embedder

    @property
    def wechatpadpro_token(self) -> str:
        return self.env.wechatpadpro_token or self.cfg.wechatpadpro.token


def _find_project_root() -> Path:
    env_root = os.getenv("PERSONA_ROOT")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd()
    for cand in (here, *here.parents):
        if (cand / "pyproject.toml").exists() and (cand / "persona").is_dir():
            return cand
    return here


def _load_toml(root: Path) -> TomlConfig:
    path = root / "config.toml"
    if not path.exists():
        return TomlConfig()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return TomlConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = _find_project_root()
    return Settings(env=EnvSettings(), cfg=_load_toml(root), project_root=root)


def reset_settings_cache() -> None:
    """For tests that mutate env/files between cases."""
    get_settings.cache_clear()
