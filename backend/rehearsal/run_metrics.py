"""Agent 运行可观测性：聚合用户自己的运行记录和失败步骤。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from backend.rehearsal.models import (
    AgentFailureStep,
    AgentRunMetricItem,
    AgentRunMetricsResponse,
    AgentRunRecord,
)


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator * 100 / denominator, 1)


class AgentRunMetricsAgent:
    """Turn persisted Agent runs into bounded, explainable health signals."""

    def summarize(
        self,
        records: list[AgentRunRecord],
        *,
        window_days: int = 30,
        as_of: datetime | None = None,
    ) -> AgentRunMetricsResponse:
        if not 7 <= window_days <= 365:
            raise ValueError("运行统计窗口必须在 7 到 365 天之间")

        end = as_of or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = end - timedelta(days=window_days)
        selected: list[tuple[datetime, AgentRunRecord]] = []
        for record in records:
            created_at = _parse_datetime(record.created_at)
            if created_at is not None and start <= created_at <= end:
                selected.append((created_at, record))
        selected.sort(key=lambda item: item[0], reverse=True)
        current_records = [record for _, record in selected]

        total_runs = len(current_records)
        completed_runs = sum(record.status == "completed" for record in current_records)
        fallback_runs = sum(record.status == "fallback" for record in current_records)
        failed_runs = sum(record.status == "failed" for record in current_records)
        average_duration_ms = round(
            sum(record.duration_ms for record in current_records) / total_runs
        ) if total_runs else 0

        grouped: dict[str, list[AgentRunRecord]] = defaultdict(list)
        for record in current_records:
            grouped[record.agent].append(record)
        by_agent = []
        for agent, agent_records in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            agent_total = len(agent_records)
            agent_failed = sum(record.status == "failed" for record in agent_records)
            agent_fallback = sum(record.status == "fallback" for record in agent_records)
            by_agent.append(AgentRunMetricItem(
                agent=agent,
                run_count=agent_total,
                completed_count=sum(record.status == "completed" for record in agent_records),
                fallback_count=agent_fallback,
                failed_count=agent_failed,
                failure_rate=_rate(agent_failed, agent_total),
                fallback_rate=_rate(agent_fallback, agent_total),
                average_duration_ms=round(sum(record.duration_ms for record in agent_records) / agent_total),
            ))

        failed_step_counts: Counter[str] = Counter()
        failed_step_summaries: dict[str, str] = {}
        for record in current_records:
            for step in record.trace:
                if step.status == "failed":
                    failed_step_counts[step.name] += 1
                    failed_step_summaries.setdefault(step.name, step.summary)
        failed_steps = [
            AgentFailureStep(
                name=name,
                failed_count=count,
                last_summary=failed_step_summaries.get(name, ""),
            )
            for name, count in failed_step_counts.most_common(8)
        ]

        return AgentRunMetricsResponse(
            window_days=window_days,
            from_datetime=start.isoformat(),
            to_datetime=end.isoformat(),
            total_runs=total_runs,
            completed_runs=completed_runs,
            fallback_runs=fallback_runs,
            failed_runs=failed_runs,
            failure_rate=_rate(failed_runs, total_runs),
            fallback_rate=_rate(fallback_runs, total_runs),
            average_duration_ms=average_duration_ms,
            by_agent=by_agent,
            failed_steps=failed_steps,
            note="指标只统计当前用户在时间窗口内的 Agent 运行记录；失败步骤来自结构化 trace，不把降级误报为失败。",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
