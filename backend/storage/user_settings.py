"""Persistence helpers for per-user training settings and provider overrides."""

import json

from backend.config import settings
from backend.models import EmbeddingSettings, LLMSettings, ServiceSettings, UserSettings


def load_user_provider(user_id: str) -> tuple[LLMSettings | None, EmbeddingSettings | None]:
    """Load per-user LLM/Embedding overrides. Returns None blocks when unset so the
    resolver falls back to the global .env defaults wholesale."""
    path = settings.user_provider_path(user_id)
    if not path.exists():
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    llm = LLMSettings(**data["llm"]) if data.get("llm") else None
    embedding = EmbeddingSettings(**data["embedding"]) if data.get("embedding") else None
    return llm, embedding


def load_user_services(user_id: str) -> ServiceSettings:
    """Per-user optional service credentials (DashScope/Tavily/OSS). Empty when unset."""
    path = settings.user_provider_path(user_id)
    if not path.exists():
        return ServiceSettings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return ServiceSettings(**data["services"]) if data.get("services") else ServiceSettings()


def save_user_provider(
    user_id: str,
    llm: LLMSettings,
    embedding: EmbeddingSettings,
    services: ServiceSettings | None = None,
):
    path = settings.user_provider_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"llm": llm.model_dump(), "embedding": embedding.model_dump()}
    if services is not None:
        data["services"] = services.model_dump()
    elif path.exists():
        # Preserve existing service creds when a caller only updates llm/embedding.
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("services"):
            data["services"] = existing["services"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index_meta(user_id: str) -> dict:
    """向量索引元数据,目前仅 {last_rebuild_at}。未重建过时为空 dict。"""
    path = settings.user_index_meta_path(user_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_index_meta(user_id: str, meta: dict):
    path = settings.user_index_meta_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_user_settings(user_id: str) -> UserSettings:
    path = settings.user_settings_path(user_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserSettings(**data)
    return UserSettings()


def save_user_settings(user_settings: UserSettings, user_id: str):
    path = settings.user_settings_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(user_settings.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
