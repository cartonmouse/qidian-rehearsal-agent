"""排练调度 Agent 的第一版：把确认后的场次转成可执行任务草案。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from backend.rehearsal.finance_agent import ResourceFinanceAgent
from backend.rehearsal.models import (
    AvailabilitySlot,
    BudgetLineItem,
    CostumeRequirement,
    InvoiceRecord,
    MusicTimelineNote,
    ScheduleAlternative,
    ScheduleDraft,
    ScheduleManualOverride,
    ScheduleOverrideRequest,
    ScheduleResourceContext,
    ScheduleTask,
    ScheduleToolCall,
    ScriptAnalysis,
    ResourceInventoryItem,
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


def _normalize_label(value: str) -> str:
    return "".join(value.strip().casefold().split())


def _costume_capacity_snapshot(inventory: list[ResourceInventoryItem]) -> dict[str, int]:
    """Sum usable costume quantities while keeping unavailable records conservative."""
    display_names: dict[str, str] = {}
    quantities: defaultdict[str, int] = defaultdict(int)
    known: list[str] = []
    for item in inventory:
        if item.category != "costume":
            continue
        key = _normalize_label(item.name)
        if not key:
            continue
        if key not in display_names:
            display_names[key] = item.name
            known.append(key)
        if item.status == "available" and item.quantity > 0:
            quantities[key] += item.quantity
    return {
        display_names[key]: max(1, quantities.get(key, 0))
        for key in known
    }


def _task_resource_requirements(
    task: ScheduleTask,
    resource_context: ScheduleResourceContext | None,
) -> list[tuple[str, str, str, int]]:
    costume_capacities = {
        _normalize_label(name): max(1, capacity)
        for name, capacity in (resource_context.costume_capacities if resource_context else {}).items()
    }
    requirements = [
        (f"actor:{actor}", "actor", actor, 1)
        for actor in _unique(task.required_characters)
    ]
    requirements.extend(
        (f"prop:{prop}", "prop", prop, 1)
        for prop in _unique(task.props)
    )
    requirements.extend(
        (
            f"costume:{_normalize_label(costume)}",
            "costume",
            costume,
            costume_capacities.get(_normalize_label(costume), 1),
        )
        for costume in _unique(task.costumes)
    )
    return requirements


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
        music_notes: list[MusicTimelineNote] | None = None,
        budget_items: list[BudgetLineItem] | None = None,
        invoices: list[InvoiceRecord] | None = None,
        inventory: list[ResourceInventoryItem] | None = None,
    ) -> ScheduleDraft:
        if analysis.review_status == "pending" and not preview:
            raise ValueError("剧本尚未完成人工确认，不能生成排练调度")

        groups: list[set[str]] = []
        costume_usage: list[dict[str, int]] = []
        tasks: list[ScheduleTask] = []
        tool_calls: list[ScheduleToolCall] = []
        resource_context = self._build_resource_context(
            music_notes,
            budget_items,
            invoices,
            inventory,
            analysis.costumes,
        )
        costume_capacities = {
            _normalize_label(name): capacity
            for name, capacity in (resource_context.costume_capacities if resource_context else {}).items()
        }
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
            costumes = _unique(scene.costumes)
            resources = {
                *(f"character:{name}" for name in characters),
                *(f"prop:{name}" for name in props),
                *(f"costume:{name}" for name in costumes),
            }
            group_conflicts: dict[int, list[str]] = {}
            for index, occupied in enumerate(groups, start=1):
                shared_resources = {
                    resource
                    for resource in resources & occupied
                    if not resource.startswith("costume:")
                }
                capacity_conflicts: list[str] = []
                for costume in costumes:
                    costume_key = _normalize_label(costume)
                    capacity = costume_capacities.get(costume_key, 1)
                    if costume_usage[index - 1].get(costume_key, 0) + 1 > capacity:
                        capacity_conflicts.append(f"{costume}（库存容量 {capacity}）")
                if shared_resources or capacity_conflicts:
                    group_conflicts[index] = [
                        *(f"共享资源:{resource.split(':', 1)[1]}" for resource in sorted(shared_resources)),
                        *(f"容量限制:{item}" for item in capacity_conflicts),
                    ]
            conflicting_groups = list(group_conflicts)
            group_index = next(
                (index for index in range(1, len(groups) + 1) if index not in group_conflicts),
                len(groups) + 1,
            )
            if group_index > len(groups):
                groups.append(set())
                costume_usage.append({})
            groups[group_index - 1].update(resources)
            for costume in costumes:
                costume_key = _normalize_label(costume)
                costume_usage[group_index - 1][costume_key] = (
                    costume_usage[group_index - 1].get(costume_key, 0) + 1
                )

            if not conflicting_groups:
                parallel_reason = "与已有任务没有超出演员、道具或服装库存容量"
            else:
                conflict_details = [
                    detail
                    for index in conflicting_groups
                    for detail in group_conflicts[index]
                ]
                shared_details = [
                    detail.removeprefix("共享资源:")
                    for detail in conflict_details
                    if detail.startswith("共享资源:")
                ]
                capacity_details = [
                    detail.removeprefix("容量限制:")
                    for detail in conflict_details
                    if detail.startswith("容量限制:")
                ]
                reason_parts = []
                if shared_details:
                    reason_parts.append(f"共享资源：{'、'.join(dict.fromkeys(shared_details))}")
                if capacity_details:
                    reason_parts.append(f"服装库存容量受限：{'、'.join(dict.fromkeys(capacity_details))}")
                parallel_reason = (
                    f"与并行组 {', '.join(str(index) for index in conflicting_groups)} "
                    + "；".join(reason_parts)
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
                costumes=costumes,
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
                    "costumes": costumes,
                    "estimated_minutes": estimated_minutes,
                },
                summary=(
                    f"第 {scene.number} 场需要 {len(characters)} 名演员、"
                    f"{len(props)} 件道具、{len(costumes)} 项服装，预计 {estimated_minutes} 分钟。"
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
                "costume_capacities": {
                    name: capacity
                    for name, capacity in (resource_context.costume_capacities if resource_context else {}).items()
                },
            },
            summary=f"根据演员、道具和服装库存容量划分为 {len(groups)} 个并行组。",
        )
        if resource_context is not None:
            self._record_tool_call(
                tool_calls,
                tool_name="inspect_rehearsal_resources",
                phase="inspect",
                arguments={
                    "music_note_count": len(resource_context.music_cues),
                    "budget_item_count": len(resource_context.budget_items),
                    "invoice_count": len(resource_context.invoices),
                    "costume_inventory_count": len(resource_context.costume_inventory),
                    "costume_capacities": resource_context.costume_capacities,
                    "costume_requirement_count": len(resource_context.costume_requirements),
                    "estimated_total": resource_context.estimated_total,
                    "actual_total": resource_context.actual_total,
                    "invoice_total": resource_context.invoice_total,
                    "verified_invoice_total": resource_context.verified_invoice_total,
                },
                result={
                    "music_cue_count": len(resource_context.music_cues),
                    "budget_item_count": len(resource_context.budget_items),
                    "invoice_count": len(resource_context.invoices),
                    "costume_inventory_count": len(resource_context.costume_inventory),
                    "costume_issue_count": resource_context.costume_issue_count,
                    "costume_capacities": resource_context.costume_capacities,
                    "costume_requirement_count": len(resource_context.costume_requirements),
                    "unmatched_costume_requirement_count": resource_context.unmatched_costume_requirement_count,
                    "budget_variance": round(
                        resource_context.actual_total - resource_context.estimated_total,
                        2,
                    ),
                    "invoice_total": resource_context.invoice_total,
                    "verified_invoice_total": resource_context.verified_invoice_total,
                    "unlinked_invoice_count": resource_context.unlinked_invoice_count,
                    "warning_count": len(resource_context.warnings),
                },
                summary=(
                    f"读取 {len(resource_context.music_cues)} 个配乐提示点和 "
                    f"{len(resource_context.budget_items)} 个预算项目、"
                    f"{len(resource_context.invoices)} 张发票、"
                    f"{len(resource_context.costume_inventory)} 条服装库存和 "
                    f"{len(resource_context.costume_requirements)} 项剧本服装需求，供排练任务复核。"
                ),
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
            resource_context=resource_context,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _build_resource_context(
        music_notes: list[MusicTimelineNote] | None,
        budget_items: list[BudgetLineItem] | None,
        invoices: list[InvoiceRecord] | None,
        inventory: list[ResourceInventoryItem] | None,
        costume_requirements: list[CostumeRequirement] | None,
    ) -> ScheduleResourceContext | None:
        music_cues = list(music_notes or [])
        items = list(budget_items or [])
        invoice_records = list(invoices or [])
        costumes = [item for item in inventory or [] if item.category == "costume"]
        costume_capacities = _costume_capacity_snapshot(costumes)
        requirements = list(costume_requirements or [])
        costume_issues = [
            item for item in costumes
            if item.status != "available" or item.quantity <= 0
        ]
        if not music_cues and not items and not invoice_records and not costumes and not requirements:
            return None

        finance = ResourceFinanceAgent().summarize(items, invoice_records)
        valid_budget_ids = {
            item.budget_item_id
            for item in items
            if item.status != "cancelled"
        }
        accepted_invoices = [
            invoice for invoice in invoice_records
            if invoice.status != "rejected"
        ]
        unlinked_invoice_count = sum(
            invoice.budget_item_id not in valid_budget_ids
            for invoice in accepted_invoices
        )
        warnings = list(finance.warnings)
        if costume_issues:
            status_labels = {"maintenance": "维修中", "missing": "缺失", "available": "数量为 0"}
            labels = "、".join(
                f"{item.name}（{status_labels.get(item.status, item.status)}）"
                for item in costume_issues
            )
            warnings.append(f"服装库存存在不可直接使用项：{labels}，请人工确认。")
        inventory_names = {_normalize_label(item.name) for item in costumes}
        unmatched_requirements = [
            requirement for requirement in requirements
            if _normalize_label(requirement.name) not in inventory_names
        ]
        if unmatched_requirements:
            labels = "、".join(
                f"{requirement.name}（{', '.join(requirement.scene_ids)}）"
                for requirement in unmatched_requirements
            )
            warnings.append(f"剧本识别出未匹配服装需求：{labels}，请补充库存或人工确认。")
        return ScheduleResourceContext(
            music_cues=music_cues,
            budget_items=items,
            invoices=invoice_records,
            costume_inventory=costumes,
            costume_capacities=costume_capacities,
            costume_requirements=requirements,
            estimated_total=finance.estimated_total,
            actual_total=finance.actual_total,
            invoice_total=finance.invoice_total,
            verified_invoice_total=finance.verified_invoice_total,
            unlinked_invoice_count=unlinked_invoice_count,
            costume_issue_count=len(costume_issues),
            unmatched_costume_requirement_count=len(unmatched_requirements),
            warnings=warnings,
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
        busy_resources: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        planned: list[ScheduleTask] = []
        tool_calls = list(draft.tool_calls)
        for task in sorted(draft.tasks, key=lambda item: (item.parallel_group, item.scene_number)):
            actors = task.required_characters or sorted(slots_by_actor)
            resource_requirements = _task_resource_requirements(task, draft.resource_context)
            assignment, reason = self._find_interval(
                actors=actors,
                duration=task.estimated_minutes,
                slots_by_actor=slots_by_actor,
                busy=busy,
                resources=resource_requirements,
                busy_resources=busy_resources,
            )
            if assignment is None:
                alternatives = self._build_alternatives(
                    task=task,
                    actors=actors,
                    reason=reason,
                    slots_by_actor=slots_by_actor,
                    busy=busy,
                    resources=resource_requirements,
                    busy_resources=busy_resources,
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
                        "resources": [
                            {"kind": kind, "name": label, "capacity": capacity}
                            for _, kind, label, capacity in resource_requirements
                            if kind != "actor"
                        ],
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
            for resource_key, _, _, _ in resource_requirements:
                busy_resources[resource_key].append((date, start, end))
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
                    "resources": [
                        {"kind": kind, "name": label, "capacity": capacity}
                        for _, kind, label, capacity in resource_requirements
                        if kind != "actor"
                    ],
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

        conflict = self._find_batch_resource_conflict(draft, validated, set(selected_ids))
        if conflict is not None:
            kind, label, capacity, left, right = conflict
            left_task, left_source = left[0], left[1]
            right_task, right_source = right[0], right[1]
            prefix = (
                "批量确认存在资源冲突"
                if left_source == right_source == "batch"
                else "批量确认与已有排班冲突"
            )
            if kind == "costume":
                raise ValueError(
                    f"{prefix}：第 {left_task.scene_number} 场与第 {right_task.scene_number} 场"
                    f"共同需要服装“{label}”，超出库存容量 {capacity} 件"
                )
            resource_label = "演员" if kind == "actor" else "道具"
            raise ValueError(
                f"{prefix}：第 {left_task.scene_number} 场与第 {right_task.scene_number} 场"
                f"共享{resource_label}:{label}"
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

    def _find_batch_resource_conflict(
        self,
        draft: ScheduleDraft,
        validated: list[tuple[ScheduleTask, ScheduleOverrideRequest, int, int]],
        selected_ids: set[str],
    ) -> tuple[str, str, int, tuple[ScheduleTask, str, str, int, int], tuple[ScheduleTask, str, str, int, int]] | None:
        """Find one explainable overlap while respecting costume quantities.

        Actors and props have an implicit capacity of one. Costume capacity is
        read from the same resource snapshot used for parallel grouping, so a
        batch can confirm two simultaneous scenes when two usable copies exist.
        Existing schedule conflicts are tolerated until a newly selected task
        participates in the overlap; the batch validator should not reject a
        pre-existing inconsistency on its own.
        """
        candidates: list[tuple[ScheduleTask, str, str, int, int]] = [
            (task, "batch", item.date, start, end)
            for task, item, start, end in validated
        ]
        for task in draft.tasks:
            if task.task_id in selected_ids or not task.scheduled_date:
                continue
            candidates.append((
                task,
                "existing",
                task.scheduled_date,
                self._to_minutes(task.scheduled_start or "00:00"),
                self._to_minutes(task.scheduled_end or "00:00"),
            ))

        costume_capacities = {
            _normalize_label(name): max(1, capacity)
            for name, capacity in (draft.resource_context.costume_capacities if draft.resource_context else {}).items()
        }
        events: dict[tuple[str, str, str], list[tuple[int, int, int]]] = defaultdict(list)
        labels: dict[tuple[str, str, str], tuple[str, int]] = {}
        for candidate_index, (task, _, date, start, end) in enumerate(candidates):
            entries = [
                ("actor", actor, 1)
                for actor in _unique(task.required_characters)
            ]
            entries.extend(
                ("prop", prop, 1)
                for prop in _unique(task.props)
            )
            entries.extend(
                (
                    "costume",
                    costume,
                    costume_capacities.get(_normalize_label(costume), 1),
                )
                for costume in _unique(task.costumes)
            )
            for kind, label, capacity in entries:
                resource_key = _normalize_label(label) if kind == "costume" else label
                key = (date, kind, resource_key)
                labels[key] = (label, capacity)
                events[key].append((start, 1, candidate_index))
                events[key].append((end, 0, candidate_index))

        for key in sorted(events):
            active: list[int] = []
            _, kind, _ = key
            label, capacity = labels[key]
            for _, event_type, candidate_index in sorted(events[key], key=lambda item: (item[0], item[1], item[2])):
                if event_type == 0:
                    if candidate_index in active:
                        active.remove(candidate_index)
                    continue
                overlapping = [*active, candidate_index]
                if len(overlapping) > capacity:
                    selected = [index for index in overlapping if candidates[index][1] == "batch"]
                    if selected:
                        if candidates[candidate_index][1] == "batch":
                            selected_index = candidate_index
                            other_index = next(index for index in active if index != selected_index)
                        else:
                            selected_index = next(index for index in active if candidates[index][1] == "batch")
                            other_index = candidate_index
                        return (
                            kind,
                            label,
                            capacity,
                            candidates[selected_index],
                            candidates[other_index],
                        )
                active.append(candidate_index)
        return None

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
        resources: list[tuple[str, str, str, int]] | None = None,
        busy_resources: dict[str, list[tuple[str, int, int]]] | None = None,
    ) -> tuple[tuple[str, int, int] | None, str]:
        required_resources = resources or []
        occupied_resources = busy_resources or {}
        missing = [actor for actor in actors if actor not in slots_by_actor]
        if missing:
            return None, f"缺少演员可用时间：{'、'.join(missing)}"

        resource_blocked = False
        resource_blocker_labels: list[str] = []
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
            boundaries.update(
                boundary
                for resource_key, _, _, _ in required_resources
                for busy_date, start, end in occupied_resources.get(resource_key, [])
                if busy_date == date
                for boundary in (start, end)
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
                conflicts = [
                    f"{label}（库存容量 {capacity}）" if kind == "costume" else f"{label}（容量 {capacity}）"
                    for resource_key, kind, label, capacity in required_resources
                    if sum(
                        not (end <= busy_start or start >= busy_end)
                        for busy_date, busy_start, busy_end in occupied_resources.get(resource_key, [])
                        if busy_date == date
                    ) >= capacity
                ]
                if conflicts:
                    resource_blocked = True
                    resource_blocker_labels.extend(conflicts)
                    continue
                return (date, start, end), ""

        if resource_blocked:
            labels = "、".join(dict.fromkeys(resource_blocker_labels))
            return None, f"排练资源没有可用并行容量：{labels}"
        return None, "演员之间没有共同的空闲时间段"

    def _build_alternatives(
        self,
        *,
        task: ScheduleTask,
        actors: list[str],
        reason: str,
        slots_by_actor: dict[str, list[tuple[str, int, int]]],
        busy: dict[str, list[tuple[str, int, int]]],
        resources: list[tuple[str, str, str, int]] | None = None,
        busy_resources: dict[str, list[tuple[str, int, int]]] | None = None,
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
                resources=resources,
                busy_resources=busy_resources,
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
