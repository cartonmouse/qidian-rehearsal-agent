"""排练调度 Agent 的第一版：把确认后的场次转成可执行任务草案。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from backend.rehearsal.models import (
    AvailabilitySlot,
    ScheduleAlternative,
    ScheduleDraft,
    ScheduleManualOverride,
    ScheduleOverrideRequest,
    ScheduleTask,
    ScheduleToolCall,
    ScriptAnalysis,
    RoomBooking,
)
from backend.rehearsal.resource_agent import room_booking_conflicts


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
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
        root_run_id: str | None = None,
    ) -> ScheduleDraft:
        if analysis.review_status == "pending" and not preview:
            raise ValueError("剧本尚未完成人工确认，不能生成排练调度")

        groups: list[set[str]] = []
        tasks: list[ScheduleTask] = []
        tool_calls: list[ScheduleToolCall] = []
        self._record_tool_call(
            tool_calls,
            tool_name="inspect_script",
            phase="inspect",
            arguments={
                "script_id": analysis.script_id,
                "scene_count": len(analysis.scenes),
                "review_status": analysis.review_status,
                "preview": preview,
            },
            result={"review_gate": "passed" if analysis.review_status != "pending" or preview else "blocked"},
            summary=(
                "剧本已确认，允许生成正式调度。"
                if analysis.review_status != "pending"
                else "当前为预览模式，保留人工确认门槛。"
            ),
        )
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
            self._record_tool_call(
                tool_calls,
                tool_name="extract_scene_requirements",
                phase="extract",
                arguments={
                    "scene_id": scene.scene_id,
                    "scene_number": scene.number,
                },
                result={
                    "required_characters": characters,
                    "props": props,
                    "estimated_minutes": estimated_minutes,
                },
                summary=(
                    f"第 {scene.number} 场需要 {len(characters)} 名演员、"
                    f"{len(props)} 件道具，预计 {estimated_minutes} 分钟。"
                ),
            )

        self._record_tool_call(
            tool_calls,
            tool_name="group_parallel_tasks",
            phase="group",
            arguments={"task_count": len(tasks)},
            result={
                "parallel_group_count": len(groups),
                "groups": [sorted(resources) for resources in groups],
            },
            summary=f"根据演员和道具资源冲突划分为 {len(groups)} 个并行组。",
        )
        self._record_tool_call(
            tool_calls,
            tool_name="validate_schedule_draft",
            phase="validate",
            arguments={"task_count": len(tasks)},
            result={"draft_valid": True, "unassigned_count": 0},
            summary="调度草案结构完整，等待演员档期匹配。",
        )

        return ScheduleDraft(
            script_id=analysis.script_id,
            review_status=analysis.review_status,
            is_preview=preview,
            agent_run_id=agent_run_id,
            parent_run_id=parent_run_id,
            root_run_id=root_run_id or agent_run_id,
            tasks=tasks,
            tool_calls=tool_calls,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def assign(
        self,
        draft: ScheduleDraft,
        slots: list[AvailabilitySlot],
        *,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
        root_run_id: str | None = None,
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
        tool_calls = list(draft.tool_calls)
        for task in sorted(draft.tasks, key=lambda item: (item.parallel_group, item.scene_number)):
            actors = task.required_characters or sorted(slots_by_actor)
            assignment, reason = self._find_interval(
                actors=actors,
                duration=task.estimated_minutes,
                slots_by_actor=slots_by_actor,
                busy=busy,
            )
            if assignment is None:
                alternatives = self._build_alternatives(
                    task=task,
                    actors=actors,
                    reason=reason,
                    slots_by_actor=slots_by_actor,
                    busy=busy,
                )
                conflict_priority = "medium" if any(
                    alternative.kind == "shorten_duration" for alternative in alternatives
                ) else "high"
                self._record_tool_call(
                    tool_calls,
                    tool_name="find_common_actor_slot",
                    phase="assign",
                    arguments={
                        "task_id": task.task_id,
                        "scene_number": task.scene_number,
                        "actors": actors,
                        "duration_minutes": task.estimated_minutes,
                    },
                    result={
                        "status": "unassigned",
                        "reason": reason,
                        "conflict_priority": conflict_priority,
                        "alternatives": [alternative.model_dump(mode="json") for alternative in alternatives],
                    },
                    status="repaired",
                    summary=(
                        f"第 {task.scene_number} 场未找到共同档期：{reason}；"
                        f"提供 {len(alternatives)} 个候选方案。"
                    ),
                )
                planned.append(task.model_copy(update={
                    "scheduled_date": None,
                    "scheduled_start": None,
                    "scheduled_end": None,
                    "unassigned_reason": reason,
                    "conflict_priority": conflict_priority,
                    "alternatives": alternatives,
                    "manual_override": None,
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
                "conflict_priority": "none",
                "alternatives": [],
                "manual_override": None,
                "status": "scheduled",
            }))
            self._record_tool_call(
                tool_calls,
                tool_name="find_common_actor_slot",
                phase="assign",
                arguments={
                    "task_id": task.task_id,
                    "scene_number": task.scene_number,
                    "actors": actors,
                    "duration_minutes": task.estimated_minutes,
                },
                result={
                    "status": "scheduled",
                    "date": date,
                    "start": self._format_minutes(start),
                    "end": self._format_minutes(end),
                },
                summary=(
                    f"第 {task.scene_number} 场找到共同档期：{date} "
                    f"{self._format_minutes(start)}–{self._format_minutes(end)}。"
                ),
            )

        unassigned_count = sum(task.status == "unassigned" for task in planned)
        scheduled_count = len(planned) - unassigned_count
        self._record_tool_call(
            tool_calls,
            tool_name="validate_schedule",
            phase="validate",
            arguments={"task_count": len(planned)},
            result={
                "scheduled_count": scheduled_count,
                "unassigned_count": unassigned_count,
                "overlap_count": 0,
            },
            status="repaired" if unassigned_count else "completed",
            summary=(
                f"完成 {scheduled_count} 个任务排班；保留 {unassigned_count} 个未排班原因。"
            ),
        )

        resolved_parent_run_id = parent_run_id if parent_run_id is not None else draft.agent_run_id
        resolved_root_run_id = root_run_id or draft.root_run_id or draft.agent_run_id or agent_run_id
        return draft.model_copy(update={
            "agent_run_id": agent_run_id or draft.agent_run_id,
            "parent_run_id": resolved_parent_run_id,
            "root_run_id": resolved_root_run_id,
            "tasks": planned,
            "tool_calls": tool_calls,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def apply_manual_override(
        self,
        draft: ScheduleDraft,
        *,
        task_id: str,
        date: str,
        start: str,
        end: str,
        room_name: str | None = None,
        note: str = "",
        room_bookings: list[RoomBooking] | None = None,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
        root_run_id: str | None = None,
    ) -> ScheduleDraft:
        """Persist a director-approved slot without pretending it passed availability checks."""
        start_minutes = self._to_minutes(start)
        end_minutes = self._to_minutes(end)
        if end_minutes <= start_minutes:
            raise ValueError("人工覆盖的结束时间必须晚于开始时间")
        task = next((item for item in draft.tasks if item.task_id == task_id), None)
        if task is None:
            raise ValueError("找不到要覆盖的排练任务")
        duration = end_minutes - start_minutes
        if duration < task.estimated_minutes:
            raise ValueError(f"人工覆盖时长不能少于预计时长 {task.estimated_minutes} 分钟")

        room_request = ScheduleOverrideRequest(
            task_id=task_id,
            date=date,
            start=start,
            end=end,
            room_name=room_name,
            note=note,
        )
        room_slots = self._validate_room_bookings([room_request], room_bookings or [])

        override = ScheduleManualOverride(
            date=date,
            start=start,
            end=end,
            room_name=room_request.room_name,
            note=note.strip() or "导演确认后人工覆盖排班",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        updated_tasks = [item.model_copy(update={
            "scheduled_date": date,
            "scheduled_start": start,
            "scheduled_end": end,
            "unassigned_reason": None,
            "conflict_priority": "none",
            "alternatives": [],
            "manual_override": override,
            "status": "overridden",
        }) if item.task_id == task_id else item for item in draft.tasks]
        resolved_parent_run_id = parent_run_id if parent_run_id is not None else draft.agent_run_id
        resolved_root_run_id = root_run_id or draft.root_run_id or draft.agent_run_id or agent_run_id
        tool_calls = list(draft.tool_calls)
        if room_slots:
            self._record_tool_call(
                tool_calls,
                tool_name="validate_room_booking",
                phase="override",
                arguments={
                    "room_name": room_slots[0].room_name,
                    "date": room_slots[0].date,
                    "start": room_slots[0].start,
                    "end": room_slots[0].end,
                },
                result={"status": "available", "checked_count": len(room_slots), "conflict_count": 0},
                summary=f"确认排练室“{room_slots[0].room_name}”时段可用。",
            )
        self._record_tool_call(
            tool_calls,
            tool_name="apply_manual_override",
            phase="override",
            arguments={
                "task_id": task_id,
                "date": date,
                "start": start,
                "end": end,
                "room_name": override.room_name,
                "note": override.note,
            },
            result={"status": "overridden", "duration_minutes": duration},
            summary=f"导演确认人工覆盖第 {task.scene_number} 场排班，不视为演员档期校验通过。",
        )
        return draft.model_copy(update={
            "agent_run_id": agent_run_id or draft.agent_run_id,
            "parent_run_id": resolved_parent_run_id,
            "root_run_id": resolved_root_run_id,
            "tasks": updated_tasks,
            "tool_calls": tool_calls,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def apply_manual_overrides(
        self,
        draft: ScheduleDraft,
        overrides: list[ScheduleOverrideRequest],
        *,
        room_bookings: list[RoomBooking] | None = None,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
        root_run_id: str | None = None,
    ) -> ScheduleDraft:
        """Confirm several slots atomically after validating the whole batch.

        The single-task override intentionally remains permissive because it is
        an explicit director decision. A batch is different: one invalid item
        or a resource overlap must reject the complete request before anything
        is persisted, so a UI retry cannot leave a half-confirmed schedule.
        """
        if not overrides:
            raise ValueError("批量确认至少需要一个排练任务")

        task_by_id = {task.task_id: task for task in draft.tasks}
        selected_ids = [item.task_id for item in overrides]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("批量确认不能重复包含同一排练任务")

        validated: list[tuple[ScheduleTask, ScheduleOverrideRequest, int, int]] = []
        for item in overrides:
            task = task_by_id.get(item.task_id)
            if task is None:
                raise ValueError(f"找不到要批量确认的排练任务：{item.task_id}")
            if task.status == "overridden":
                raise ValueError(
                    f"第 {task.scene_number} 场已经人工确认，批量重复提交被拒绝；如需修改请使用单任务覆盖"
                )
            start_minutes = self._to_minutes(item.start)
            end_minutes = self._to_minutes(item.end)
            if end_minutes <= start_minutes:
                raise ValueError(f"第 {task.scene_number} 场人工确认的结束时间必须晚于开始时间")
            if end_minutes - start_minutes < task.estimated_minutes:
                raise ValueError(f"第 {task.scene_number} 场确认时长不能少于预计时长 {task.estimated_minutes} 分钟")
            validated.append((task, item, start_minutes, end_minutes))

        for index, (task, item, start, end) in enumerate(validated):
            for other_task, other_item, other_start, other_end in validated[index + 1:]:
                if item.date != other_item.date or end <= other_start or start >= other_end:
                    continue
                shared = self._task_resources(task) & self._task_resources(other_task)
                if shared:
                    labels = "、".join(sorted(shared))
                    raise ValueError(
                        f"批量确认存在资源冲突：第 {task.scene_number} 场与第 {other_task.scene_number} 场共享{labels}"
                    )

            for other_task in draft.tasks:
                if other_task.task_id in selected_ids or not other_task.scheduled_date:
                    continue
                if item.date != other_task.scheduled_date:
                    continue
                other_start = self._to_minutes(other_task.scheduled_start or "00:00")
                other_end = self._to_minutes(other_task.scheduled_end or "00:00")
                if end <= other_start or start >= other_end:
                    continue
                shared = self._task_resources(task) & self._task_resources(other_task)
                if shared:
                    labels = "、".join(sorted(shared))
                    raise ValueError(
                        f"批量确认与已有排班冲突：第 {task.scene_number} 场与第 {other_task.scene_number} 场共享{labels}"
                    )

        room_slots = self._validate_room_bookings(
            [item for _, item, _, _ in validated],
            room_bookings or [],
        )

        now = datetime.now(timezone.utc).isoformat()
        overrides_by_id = {
            item.task_id: (item, ScheduleManualOverride(
                date=item.date,
                start=item.start,
                end=item.end,
                room_name=item.room_name,
                note=item.note.strip() or "导演批量确认排班",
                created_at=now,
            ))
            for _, item, _, _ in validated
        }
        updated_tasks: list[ScheduleTask] = []
        for task in draft.tasks:
            pair = overrides_by_id.get(task.task_id)
            if pair is None:
                updated_tasks.append(task)
                continue
            item, override = pair
            updated_tasks.append(task.model_copy(update={
                "scheduled_date": item.date,
                "scheduled_start": item.start,
                "scheduled_end": item.end,
                "unassigned_reason": None,
                "conflict_priority": "none",
                "alternatives": [],
                "manual_override": override,
                "status": "overridden",
            }))
        resolved_parent_run_id = parent_run_id if parent_run_id is not None else draft.agent_run_id
        resolved_root_run_id = root_run_id or draft.root_run_id or draft.agent_run_id or agent_run_id
        tool_calls = list(draft.tool_calls)
        if room_slots:
            self._record_tool_call(
                tool_calls,
                tool_name="validate_room_booking",
                phase="override",
                arguments={
                    "room_slots": [
                        {
                            "room_name": item.room_name,
                            "date": item.date,
                            "start": item.start,
                            "end": item.end,
                        }
                        for item in room_slots
                    ],
                },
                result={"status": "available", "checked_count": len(room_slots), "conflict_count": 0},
                summary=f"确认 {len(room_slots)} 个排练室时段均可用。",
            )
        self._record_tool_call(
            tool_calls,
            tool_name="apply_manual_override_batch",
            phase="override",
            arguments={
                "task_ids": selected_ids,
                "override_count": len(selected_ids),
                "room_names": sorted({item.room_name for item in room_slots if item.room_name}),
            },
            result={
                "status": "overridden",
                "confirmed_task_ids": selected_ids,
                "overridden_count": len(selected_ids),
                "atomic": True,
            },
            summary=f"导演一次确认 {len(selected_ids)} 个排练任务；本批次已原子写入。",
        )
        return draft.model_copy(update={
            "agent_run_id": agent_run_id or draft.agent_run_id,
            "parent_run_id": resolved_parent_run_id,
            "root_run_id": resolved_root_run_id,
            "tasks": updated_tasks,
            "tool_calls": tool_calls,
            "created_at": now,
        })

    @staticmethod
    def _task_resources(task: ScheduleTask) -> set[str]:
        return {
            *(f"演员:{actor}" for actor in task.required_characters),
            *(f"道具:{prop}" for prop in task.props),
        }

    @staticmethod
    def _validate_room_bookings(
        overrides: list[ScheduleOverrideRequest],
        existing: list[RoomBooking],
    ) -> list[ScheduleOverrideRequest]:
        room_overrides = [item for item in overrides if item.room_name]
        candidates = [
            (
                item,
                RoomBooking(
                    booking_id=f"schedule-room-{item.task_id}",
                    room_name=item.room_name or "",
                    date=item.date,
                    start=item.start,
                    end=item.end,
                ),
            )
            for item in room_overrides
        ]
        for item, candidate in candidates:
            conflict = next(
                (booking for booking in existing if room_booking_conflicts(candidate, booking)),
                None,
            )
            if conflict is not None:
                raise ValueError(
                    f"排练室“{candidate.room_name}”在 {candidate.date} "
                    f"{candidate.start}-{candidate.end} 已有预约（{conflict.start}-{conflict.end}）"
                )

        for index, (item, candidate) in enumerate(candidates):
            for other_item, other_candidate in candidates[index + 1:]:
                if room_booking_conflicts(candidate, other_candidate):
                    raise ValueError(
                        f"批量确认存在排练室冲突：任务 {item.task_id} 与 {other_item.task_id} "
                        f"占用“{candidate.room_name}”的重叠时段"
                    )
        return room_overrides

    @staticmethod
    def _record_tool_call(
        calls: list[ScheduleToolCall],
        *,
        tool_name: str,
        phase: str,
        arguments: dict,
        result: dict,
        summary: str,
        status: str = "completed",
    ) -> None:
        calls.append(ScheduleToolCall(
            call_id=f"schedule-tool-{len(calls) + 1:02d}",
            tool_name=tool_name,
            phase=phase,  # type: ignore[arg-type]
            arguments=arguments,
            result=result,
            status=status,  # type: ignore[arg-type]
            summary=summary,
        ))

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

    def _build_alternatives(
        self,
        *,
        task: ScheduleTask,
        actors: list[str],
        reason: str,
        slots_by_actor: dict[str, list[tuple[str, int, int]]],
        busy: dict[str, list[tuple[str, int, int]]],
    ) -> list[ScheduleAlternative]:
        """Offer deterministic, reviewable next actions instead of returning a dead end."""
        missing = [actor for actor in actors if actor not in slots_by_actor]
        alternatives: list[ScheduleAlternative] = []
        if missing:
            alternatives.append(ScheduleAlternative(
                alternative_id=f"{task.task_id}-alt-1",
                kind="request_availability",
                label="补齐缺失演员档期",
                reason=f"当前没有这些演员的可用时间：{'、'.join(missing)}。",
                affected_actors=missing,
                priority="high",
            ))
            return alternatives

        candidates = list(range(task.estimated_minutes - 15, 14, -15))
        if task.estimated_minutes > 15 and 15 not in candidates:
            candidates.append(15)
        for duration in candidates:
            assignment, _ = self._find_interval(
                actors=actors,
                duration=duration,
                slots_by_actor=slots_by_actor,
                busy=busy,
            )
            if assignment is None:
                continue
            date, start, end = assignment
            alternatives.append(ScheduleAlternative(
                alternative_id=f"{task.task_id}-alt-{len(alternatives) + 1}",
                kind="shorten_duration",
                label=f"压缩为 {duration} 分钟",
                reason="完整排练时长没有共同区间，但所有演员存在较短的共同空闲时间。",
                affected_actors=actors,
                date=date,
                start=self._format_minutes(start),
                end=self._format_minutes(end),
                duration_minutes=duration,
                priority="medium",
            ))
            break

        if len(actors) > 1:
            alternatives.append(ScheduleAlternative(
                alternative_id=f"{task.task_id}-alt-{len(alternatives) + 1}",
                kind="split_by_actor",
                label="拆分为分组排练",
                reason=f"完整合排需要 {'、'.join(actors)} 同时到场，可先按角色分组完成对词或走位。",
                affected_actors=actors,
                priority="high",
            ))
        else:
            alternatives.append(ScheduleAlternative(
                alternative_id=f"{task.task_id}-alt-{len(alternatives) + 1}",
                kind="request_availability",
                label="增加或延长演员档期",
                reason=reason,
                affected_actors=actors,
                priority="high",
            ))
        return alternatives
