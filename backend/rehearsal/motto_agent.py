"""格言表 Agent：保存剧团认为值得反复带回排练场的话。"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.rehearsal.models import MottoRequest, MottoResponse, MottoUpdateRequest


_THEME_TAGS = {
    "performance": "表演",
    "team": "协作",
    "theatre": "戏剧",
    "life": "生活",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MottoAgent:
    """Keep the quote exact and only add lightweight, explainable metadata."""

    def record(
        self,
        request: MottoRequest,
        *,
        motto_id: str,
        script_title: str = "",
        scene_title: str = "",
    ) -> MottoResponse:
        tags = list(request.tags)
        theme_tag = _THEME_TAGS.get(request.theme)
        if theme_tag and theme_tag not in tags:
            tags.insert(0, theme_tag)
        created_at = _now()
        return MottoResponse(
            motto_id=motto_id,
            script_id=request.script_id,
            script_title=script_title,
            scene_id=request.scene_id,
            scene_title=scene_title,
            text=request.text,
            author=request.author,
            source=request.source,
            theme=request.theme,
            tags=tags,
            favorite=False,
            created_at=created_at,
            updated_at=created_at,
        )

    def update(self, motto: MottoResponse, request: MottoUpdateRequest) -> MottoResponse:
        return motto.model_copy(update={"favorite": request.favorite, "updated_at": _now()})
