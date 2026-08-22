"""Topic management routes."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend.config import settings
from backend.indexer import invalidate_topic, load_topics, save_topics

router = APIRouter(prefix="/api")


@router.get("/topics")
def get_topics(user_id: str = Depends(get_current_user)):
    """List available drill topics (with name and icon)."""
    return load_topics(user_id)


@router.post("/topics")
def create_topic(body: dict, user_id: str = Depends(get_current_user)):
    """Add a new topic."""
    name = body.get("name", "").strip()
    icon = body.get("icon", "📝").strip()
    if not name:
        raise HTTPException(400, "name is required")

    key = body.get("key", "").strip()
    if not key:
        key = uuid.uuid4().hex[:8]
    key = re.sub(r"[^a-zA-Z0-9_-]", "", key)
    if not key:
        key = uuid.uuid4().hex[:8]

    topics = load_topics(user_id)
    if key in topics:
        raise HTTPException(409, f"Topic '{key}' already exists")

    topics[key] = {"name": name, "icon": icon, "dir": key}
    save_topics(topics, user_id)

    topic_dir = settings.user_knowledge_path(user_id) / key
    topic_dir.mkdir(parents=True, exist_ok=True)
    readme = topic_dir / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n", encoding="utf-8")

    return {"ok": True, "key": key}


@router.delete("/topics/{key}")
def delete_topic(key: str, user_id: str = Depends(get_current_user)):
    """Remove a topic."""
    topics = load_topics(user_id)
    if key not in topics:
        raise HTTPException(404, f"Topic '{key}' not found")

    del topics[key]
    save_topics(topics, user_id)
    invalidate_topic(key, user_id)
    return {"ok": True}
