"""排练调度 Agent 的第一版：把确认后的场次转成可执行任务草案。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from backend.rehearsal.models import AvailabilitySlot, ScheduleDraft, ScheduleTask, ScriptAnalysis


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


class RehearsalScheduleAgent:
    """Generate scene tasks and greedy parallel groups from a script analysis.

    A reviewed analysis is required for a formal draft. A preview is allowed
    before review so the team can inspect a possible schedule without treating
    unconfirmed scene metadata as production-ready.
    """

    def run(
        self,
        analysis: ScriptAnalysis,
        *,
        default_minutes: int = 45,
        preview: bool = False,
    ) -> ScheduleDraft:
        if analysis.review_status == "pending" and not preview:
            raise ValueError("剧本尚未完成人工确认，不能生成排练调度")

        groups: list[set[str]] = []
        tasks: list[ScheduleTask] = []
        for scene in analysis.scenes:
            characters = _unique([*scene.characters, *(line.character for line in scene.lines)])
            props = _unique(scene.props)
            resources = {
                *(f"character:{name}" for name in characters),
                *(f"prop:{name}" for name in props),
            }
            conflicting_groups = [
                index
                for index, occupied in enumerate(groups, start=1)
                if resources & occupied
            ]
            group_index = next(
                (index for index, occupied in enumerate(groups, start=1) if not resources & occupied),
                len(groups) + 1,
            )
            if group_index > len(groups):
                groups.append(set())
            groups[group_index - 1].update(resources)

            if not conflicting_groups:
                parallel_reason = "与已有任务没有共同演员或道具资源"
            else:
                conflict_resources = sorted({
                    resource.split(":", 1)[1]
                    for occupied in (groups[index - 1] for index in conflicting_groups)
                    for resource in resources & occupied
                })
                parallel_reason = (
                    f"与并行组 {', '.join(str(index) for index in conflicting_groups)} "
                    f"共享资源：{'、'.join(conflict_resources)}"
                )

            estimated_minutes = min(
                240,
                max(15, default_minutes + max(0, len(scene.lines) - 8) * 3),
            )
            tasks.append(ScheduleTask(
                task_id=f"scene-task-{scene.number}",
                scene_id=scene.scene_id,
                scene_number=scene.number,
                title=scene.title,
                required_characters=characters,
                props=props,
                estimated_minutes=estimated_minutes,
                parallel_group=group_index,
                parallel_reason=parallel_reason,
            ))

        return ScheduleDraft(
            script_id=analysis.script_id,
            review_status=analysis.review_status,
            is_preview=preview,
            tasks=tasks,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def assign(
        self,
        draft: ScheduleDraft,
        slots: list[AvailabilitySlot],
    ) -> ScheduleDraft:
        """Assign tasks to the earliest common free interval for all actors."""
        slots_by_actor: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for slot in slots:
            start = self._to_minutes(slot.start)
            end = self._to_minutes(slot.end)
            if end <= start:
                raise ValueError(f"演员 {slot.actor} 的可用时间段无效")
            slots_by_actor[slot.actor.strip()].append((slot.date, start, end))
        for actor_slots in slots_by_actor.values():
            actor_slots.sort(key=lambda item: (item[0], item[1]))

        busy: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        planned: list[ScheduleTask] = []
        for task in sorted(draft.tasks, key=lambda item: (item.parallel_group, item.scene_number)):
            actors = task.required_characters or sorted(slots_by_actor)
            assignment, reason = self._find_interval(
                actors=actors,
                duration=task.estimated_minutes,
                slots_by_actor=slots_by_actor,
                busy=busy,
            )
            if assignment is None:
                planned.append(task.model_copy(update={
                    "scheduled_date": None,
                    "scheduled_start": None,
                    "scheduled_end": None,
                    "unassigned_reason": reason,
                    "status": "unassigned",
                }))
                continue

            date, start, end = assignment
            for actor in actors:
                busy[actor].append((date, start, end))
            planned.append(task.model_copy(update={
                "scheduled_date": date,
                "scheduled_start": self._format_minutes(start),
                "scheduled_end": self._format_minutes(end),
                "unassigned_reason": None,
                "status": "scheduled",
            }))

        return draft.model_copy(update={
            "tasks": planned,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _to_minutes(value: str) -> int:
        try:
            hour, minute = (int(part) for part in value.split(":", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"无效时间：{value}") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(f"无效时间：{value}")
        return hour * 60 + minute

    @staticmethod
    def _format_minutes(value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    def _find_interval(
        self,
        *,
        actors: list[str],
        duration: int,
        slots_by_actor: dict[str, list[tuple[str, int, int]]],
        busy: dict[str, list[tuple[str, int, int]]],
    ) -> tuple[tuple[str, int, int] | None, str]:
        missing = [actor for actor in actors if actor not in slots_by_actor]
        if missing:
            return None, f"缺少演员可用时间：{'、'.join(missing)}"

        dates = sorted({date for actor in actors for date, _, _ in slots_by_actor[actor]})
        for date in dates:
            date_slots = {
                actor: [item for item in slots_by_actor[actor] if item[0] == date]
                for actor in actors
            }
            boundaries = {
                start
                for actor in actors
                for _, start, _ in date_slots[actor]
            }
            boundaries.update(
                end
                for actor in actors
                for busy_date, _, end in busy[actor]
                if busy_date == date
            )
            for start in sorted(boundaries):
                valid = True
                for actor in actors:
                    covering = [
                        end for _, slot_start, end in date_slots[actor]
                        if slot_start <= start < end and end - start >= duration
                    ]
                    if not covering:
                        valid = False
                        break
                if not valid:
                    continue
                end = start + duration
                if any(
                    busy_date == date and not (end <= busy_start or start >= busy_end)
                    for actor in actors
                    for busy_date, busy_start, busy_end in busy[actor]
                ):
                    continue
                return (date, start, end), ""

        return None, "演员之间没有共同的空闲时间段"
