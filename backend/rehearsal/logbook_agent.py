"""场记 Agent：保存原话，同时补齐可检索的剧本上下文和分类标签。"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.rehearsal.models import RehearsalLogRequest, RehearsalLogResponse


_CATEGORY_TAGS = {
    "direction": "导演",
    "actor": "演员",
    "blocking": "走位",
    "prop": "道具",
    "sound": "声音",
}


class RehearsalLogAgent:
    """Create a traceable log record without rewriting the stage manager's words."""

    def record(
        self,
        request: RehearsalLogRequest,
        *,
        log_id: str,
        script_title: str = "",
        scene_title: str = "",
    ) -> RehearsalLogResponse:
        tags = list(request.tags)
        category_tag = _CATEGORY_TAGS.get(request.category)
        if category_tag and category_tag not in tags:
            tags.insert(0, category_tag)
        return RehearsalLogResponse(
            log_id=log_id,
            script_id=request.script_id,
            script_title=script_title,
            scene_id=request.scene_id,
            scene_title=scene_title,
            rehearsal_date=request.rehearsal_date,
            author=request.author,
            category=request.category,
            content=request.content,
            tags=tags,
            source_line=request.source_line,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
