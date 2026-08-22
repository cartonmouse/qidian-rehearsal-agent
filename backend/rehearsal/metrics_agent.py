"""排练反馈度量 Agent：从已归档事实生成可回指的统计摘要。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from backend.rehearsal.models import (
    RehearsalFeedbackResponse,
    RehearsalMetricItem,
    RehearsalMetricRecentSession,
    RehearsalMetricTrend,
    RehearsalMetricsResponse,
)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100 / denominator, 1)


def _top_items(values: list[str], *, limit: int = 5) -> list[RehearsalMetricItem]:
    counts = Counter(item.strip() for item in values if item and item.strip())
    return [RehearsalMetricItem(label=label, count=count) for label, count in counts.most_common(limit)]


class RehearsalMetricsAgent:
    """Aggregate user-owned feedback without inventing a quality score."""

    def summarize(
        self,
        records: list[RehearsalFeedbackResponse],
        *,
        window_days: int = 30,
        as_of: date | None = None,
    ) -> RehearsalMetricsResponse:
        if not 7 <= window_days <= 365:
            raise ValueError("统计窗口必须在 7 到 365 天之间")

        end_date = as_of or datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=window_days - 1)
        selected: list[RehearsalFeedbackResponse] = []
        for record in records:
            rehearsal_date = _parse_date(record.rehearsal_date)
            if rehearsal_date is not None and start_date <= rehearsal_date <= end_date:
                selected.append(record)

        selected.sort(key=lambda item: (item.rehearsal_date, item.created_at), reverse=True)
        session_count = len(selected)
        output_count = sum(len(record.outputs) for record in selected)
        strength_count = sum(len(record.strengths) for record in selected)
        blocker_count = sum(len(record.blockers) for record in selected)
        next_action_count = sum(len(record.next_actions) for record in selected)
        sessions_with_outputs = sum(bool(record.outputs) for record in selected)
        sessions_with_blockers = sum(bool(record.blockers) for record in selected)
        sessions_with_next_actions = sum(bool(record.next_actions) for record in selected)
        participant_names = {
            participant.strip()
            for record in selected
            for participant in record.participants
            if participant and participant.strip()
        }

        buckets: dict[str, dict[str, int]] = defaultdict(lambda: {
            "sessions": 0,
            "outputs": 0,
            "blockers": 0,
            "next_actions": 0,
        })
        for record in selected:
            bucket = buckets[record.rehearsal_date]
            bucket["sessions"] += 1
            bucket["outputs"] += len(record.outputs)
            bucket["blockers"] += len(record.blockers)
            bucket["next_actions"] += len(record.next_actions)

        trend: list[RehearsalMetricTrend] = []
        for offset in range(window_days):
            current = start_date + timedelta(days=offset)
            key = current.isoformat()
            bucket = buckets[key]
            trend.append(RehearsalMetricTrend(date=key, **bucket))

        recent_sessions = [
            RehearsalMetricRecentSession(
                record_id=record.record_id,
                rehearsal_date=record.rehearsal_date,
                script_title=record.script_title,
                scene_title=record.scene_title,
                outputs_count=len(record.outputs),
                blockers_count=len(record.blockers),
                next_actions_count=len(record.next_actions),
                engine=record.engine,
            )
            for record in selected[:8]
        ]

        return RehearsalMetricsResponse(
            window_days=window_days,
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
            session_count=session_count,
            output_count=output_count,
            strength_count=strength_count,
            blocker_count=blocker_count,
            next_action_count=next_action_count,
            sessions_with_outputs=sessions_with_outputs,
            sessions_with_blockers=sessions_with_blockers,
            sessions_with_next_actions=sessions_with_next_actions,
            unique_participant_count=len(participant_names),
            average_participants=round(
                sum(len(record.participants) for record in selected) / session_count,
                1,
            ) if session_count else 0.0,
            output_coverage=_rate(sessions_with_outputs, session_count),
            blocker_rate=_rate(sessions_with_blockers, session_count),
            next_action_rate=_rate(sessions_with_next_actions, session_count),
            engine_counts=dict(Counter(record.engine for record in selected)),
            top_strengths=_top_items([item for record in selected for item in record.strengths]),
            top_blockers=_top_items([item for record in selected for item in record.blockers]),
            trend=trend,
            recent_sessions=recent_sessions,
            note="指标只由当前用户在统计窗口内已归档的排练反馈计算，不代表对排练质量的自动评判。",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
