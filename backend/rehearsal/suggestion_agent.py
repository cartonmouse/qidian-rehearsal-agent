"""演员建议收件箱 Agent：保留原建议并给出可解释的处理优先级。"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.rehearsal.models import SuggestionRequest, SuggestionResponse, SuggestionUpdateRequest


_HIGH_PRIORITY_MARKERS = ("安全", "危险", "受伤", "疼", "过敏", "设备故障", "冲突")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SuggestionInboxAgent:
    """Structure actor suggestions without rewriting or silently dismissing them."""

    def submit(
        self,
        request: SuggestionRequest,
        *,
        suggestion_id: str,
        script_title: str = "",
        scene_title: str = "",
    ) -> SuggestionResponse:
        priority = "high" if (
            request.category == "safety"
            or any(marker in request.content for marker in _HIGH_PRIORITY_MARKERS)
        ) else "normal"
        created_at = _now()
        return SuggestionResponse(
            suggestion_id=suggestion_id,
            script_id=request.script_id,
            script_title=script_title,
            scene_id=request.scene_id,
            scene_title=scene_title,
            actor_name=request.actor_name,
            category=request.category,
            content=request.content,
            priority=priority,
            status="new",
            created_at=created_at,
            updated_at=created_at,
        )

    def update(
        self,
        suggestion: SuggestionResponse,
        request: SuggestionUpdateRequest,
    ) -> SuggestionResponse:
        return suggestion.model_copy(update={
            "status": request.status,
            "response": request.response,
            "updated_at": _now(),
        })
