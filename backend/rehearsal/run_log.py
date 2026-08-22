"""统一记录排练 Agent 的可解释运行结果。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.rehearsal.models import AgentRunRecord, AgentStep
from backend.rehearsal.storage import save_agent_run


def outcome_status(*, engine: str | None = None, warnings: list[str] | None = None) -> str:
    """Return a stable UI status without treating a planned fallback as a failure."""
    if engine == "fallback":
        return "fallback"
    if any("回退" in item or "fallback" in item.lower() for item in warnings or []):
        return "fallback"
    return "completed"


def record_agent_run(
    *,
    user_id: str,
    agent: str,
    action: str,
    script_id: str | None,
    script_title: str,
    mode: str,
    summary: str,
    trace: list[AgentStep],
    warnings: list[str] | None = None,
    status: str = "completed",
    duration_ms: int = 0,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    root_run_id: str | None = None,
) -> AgentRunRecord:
    resolved_run_id = run_id or uuid4().hex
    record = AgentRunRecord(
        run_id=resolved_run_id,
        parent_run_id=parent_run_id,
        root_run_id=root_run_id or (parent_run_id or resolved_run_id),
        agent=agent,  # type: ignore[arg-type]
        action=action,
        script_id=script_id,
        script_title=script_title,
        mode=mode,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        trace=trace,
        warnings=list(dict.fromkeys(warnings or [])),
        duration_ms=max(0, duration_ms),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_agent_run(record, user_id=user_id)
    return record
