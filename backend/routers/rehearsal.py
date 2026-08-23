"""奇点剧团排练领域 API。"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pypdf import PdfReader

from backend.auth import get_current_user
from backend.rehearsal.agent import ScriptAnalysisAgent, summarize_costume_requirements
from backend.rehearsal.feedback_agent import RehearsalMirrorAgent
from backend.rehearsal.finance_agent import ResourceFinanceAgent
from backend.rehearsal.line_reading import LineReadingSessionAgent
from backend.rehearsal.logbook_agent import RehearsalLogAgent
from backend.rehearsal.metrics_agent import RehearsalMetricsAgent
from backend.rehearsal.motto_agent import MottoAgent
from backend.rehearsal.promo_agent import PromoCopyAgent
from backend.rehearsal.rag_agent import ScriptRagAgent
from backend.rehearsal.resource_agent import (
    CostumeCustodyAgent,
    ResourceAgent,
    ResourceAuditAgent,
    room_booking_conflicts,
)
from backend.rehearsal.run_log import outcome_status, record_agent_run
from backend.rehearsal.run_metrics import AgentRunMetricsAgent
from backend.rehearsal.schedule_agent import RehearsalScheduleAgent
from backend.rehearsal.stage_agent import StageVisualizationAgent
from backend.rehearsal.suggestion_agent import SuggestionInboxAgent
from backend.rehearsal.version_diff import ScriptVersionDiffAgent, attach_resource_audit_matches
from backend.rehearsal.models import (
    AvailabilitySlot,
    AvailabilityUpdateRequest,
    AgentRunRecord,
    AgentRunMetricsResponse,
    AgentStep,
    BudgetLineItem,
    BudgetUpdateRequest,
    Character,
    CostumeCheckoutRequest,
    CostumeCustodyAlert,
    CostumeReturnRequest,
    InvoiceRecord,
    InvoiceUpdateRequest,
    MusicTimelineNote,
    MusicTimelineUpdateRequest,
    Prop,
    RehearsalFeedbackRequest,
    RehearsalFeedbackResponse,
    RehearsalMetricsResponse,
    RehearsalLogRequest,
    RehearsalLogResponse,
    ResourceCheckRequest,
    ResourceCheckResponse,
    ResourceAuditRecord,
    ResourceInventoryItem,
    ResourceInventoryUpdateRequest,
    ResourceFinanceSummary,
    RoomBooking,
    RoomBookingRequest,
    ScriptDiffRequest,
    StageVisualization,
    ScriptVersionDiff,
    ScheduleDraft,
    ScheduleBatchOverrideRequest,
    ScheduleBatchOverrideResponse,
    ScheduleDraftRequest,
    ScheduleOverrideRequest,
    SchedulePlanRequest,
    ScriptAnalysis,
    LineReadingRequest,
    LineReadingResponse,
    LineReadingSession,
    MottoRequest,
    MottoResponse,
    MottoUpdateRequest,
    PromoCopyRequest,
    PromoCopyResponse,
    ScriptRagQueryRequest,
    ScriptRagResponse,
    ScriptParseRequest,
    ScriptReviewRequest,
    SuggestionRequest,
    SuggestionResponse,
    SuggestionUpdateRequest,
)
from backend.rehearsal.storage import (
    delete_schedule,
    get_availability,
    get_agent_run,
    list_resource_audits,
    get_budget_items,
    get_feedback,
    get_inventory,
    get_invoices,
    get_line_reading_session,
    get_motto,
    get_music_notes,
    get_schedule,
    get_script,
    get_suggestion,
    list_feedback,
    list_agent_runs,
    list_room_bookings,
    list_logs,
    list_scripts,
    list_suggestions,
    list_mottos,
    list_promo_copies,
    save_feedback,
    save_inventory,
    save_log,
    save_room_booking,
    save_schedule,
    save_availability,
    save_budget_items,
    save_script,
    save_invoices,
    save_line_reading_session,
    save_music_notes,
    delete_room_booking,
    delete_log,
    save_suggestion,
    delete_suggestion,
    save_motto,
    delete_motto,
    save_promo_copy,
    save_resource_audit,
)


router = APIRouter(prefix="/api/rehearsal", tags=["rehearsal"])
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


def _audit_resource_change(*, user_id: str, resource_type: str, operation: str, before: list, after: list) -> None:
    record = ResourceAuditAgent().compare(
        resource_type=resource_type,  # type: ignore[arg-type]
        operation=operation,  # type: ignore[arg-type]
        before=before,
        after=after,
    )
    if record is not None:
        save_resource_audit(record, user_id=user_id)


_CUSTODY_FIELDS = (
    "borrowed_quantity",
    "checked_out_to",
    "checked_out_scene_id",
    "checked_out_scene_label",
    "expected_return_date",
    "expected_return_time",
    "custody_note",
    "custody_records",
)


def _merge_inventory_custody(
    before: list[ResourceInventoryItem],
    requested: list[ResourceInventoryItem],
) -> list[ResourceInventoryItem]:
    """Keep custody state behind the explicit checkout/return actions."""
    current_by_id = {item.resource_id: item for item in before}
    requested_ids = {item.resource_id for item in requested}
    removed_active = [
        item.name
        for item in before
        if item.borrowed_quantity > 0 and item.resource_id not in requested_ids
    ]
    if removed_active:
        raise HTTPException(409, f"不能移除已借出服装，请先归还：{'、'.join(removed_active)}")

    merged: list[ResourceInventoryItem] = []
    for item in requested:
        current = current_by_id.get(item.resource_id)
        if current and current.borrowed_quantity > 0:
            if item.category != "costume":
                raise HTTPException(409, f"服装“{current.name}”仍有借出数量，不能改为道具")
            if item.quantity < current.borrowed_quantity:
                raise HTTPException(409, f"库存数量不能低于服装“{current.name}”已借出的 {current.borrowed_quantity} 件")
            item = item.model_copy(update={field: getattr(current, field) for field in _CUSTODY_FIELDS})
        elif item.borrowed_quantity > 0 or any(
            getattr(item, field)
            for field in _CUSTODY_FIELDS
            if field != "borrowed_quantity"
        ):
            raise HTTPException(409, "借还状态请使用服装借出或归还操作，不要直接修改库存快照")
        merged.append(item)
    return merged


def _replace_inventory_item(
    inventory: list[ResourceInventoryItem],
    updated: ResourceInventoryItem,
) -> list[ResourceInventoryItem]:
    return [
        updated if item.resource_id == updated.resource_id else item
        for item in inventory
    ]


@router.get("/resources/inventory", response_model=list[ResourceInventoryItem])
def read_resource_inventory(user_id: str = Depends(get_current_user)):
    """Read the current user's prop and costume inventory."""
    return get_inventory(user_id=user_id)


@router.get("/resources/inventory/custody-alerts", response_model=list[CostumeCustodyAlert])
def read_costume_custody_alerts(
    as_of: str | None = Query(default=None, max_length=50),
    user_id: str = Depends(get_current_user),
):
    """Return deterministic overdue and due-soon reminders for active custody records."""
    reference = datetime.now()
    if as_of:
        try:
            reference = datetime.fromisoformat(as_of.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(400, "as_of 必须是有效的 ISO 日期时间") from exc
    return CostumeCustodyAgent().inspect_due(
        get_inventory(user_id=user_id),
        as_of=reference,
    )


@router.put("/resources/inventory", response_model=list[ResourceInventoryItem])
def write_resource_inventory(
    request: ResourceInventoryUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Replace the current user's inventory in one explicit, reviewable action."""
    ids = [item.resource_id for item in request.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "资源记录 ID 不能重复")
    before = get_inventory(user_id=user_id)
    merged = _merge_inventory_custody(before, request.items)
    save_inventory(merged, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="inventory",
        operation="replace",
        before=before,
        after=merged,
    )
    return merged


@router.post("/resources/inventory/{resource_id}/checkout", response_model=ResourceInventoryItem)
def checkout_costume(
    resource_id: str,
    request: CostumeCheckoutRequest,
    user_id: str = Depends(get_current_user),
):
    """Record who holds a costume, for which scene, and when it should return."""
    before = get_inventory(user_id=user_id)
    try:
        updated = CostumeCustodyAgent().checkout(before, resource_id, request)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    after = _replace_inventory_item(before, updated)
    save_inventory(after, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="inventory",
        operation="checkout",
        before=before,
        after=after,
    )
    return updated


@router.post("/resources/inventory/{resource_id}/return", response_model=ResourceInventoryItem)
def return_costume(
    resource_id: str,
    request: CostumeReturnRequest,
    user_id: str = Depends(get_current_user),
):
    """Record a partial or complete costume return and clear custody on completion."""
    before = get_inventory(user_id=user_id)
    try:
        updated = CostumeCustodyAgent().return_item(before, resource_id, request)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    after = _replace_inventory_item(before, updated)
    save_inventory(after, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="inventory",
        operation="return",
        before=before,
        after=after,
    )
    return updated


@router.get("/resources/audit", response_model=list[ResourceAuditRecord])
def read_resource_audits(
    limit: int = Query(default=50, ge=1, le=200),
    resource_type: Literal["inventory", "room", "music", "budget", "invoice"] | None = Query(default=None),
    change_type: Literal["created", "updated", "deleted"] | None = Query(default=None),
    query: str | None = Query(default=None, max_length=100),
    user_id: str = Depends(get_current_user),
):
    """Read filtered, recent user-scoped changes to rehearsal resources."""
    return list_resource_audits(
        user_id=user_id,
        limit=limit,
        resource_type=resource_type,
        change_type=change_type,
        query=query,
    )


@router.get("/resources/rooms", response_model=list[RoomBooking])
def read_room_bookings(user_id: str = Depends(get_current_user)):
    return list_room_bookings(user_id=user_id)


@router.post("/resources/rooms", response_model=RoomBooking, status_code=201)
def create_room_booking(
    request: RoomBookingRequest,
    user_id: str = Depends(get_current_user),
):
    """Create a room booking while rejecting overlapping bookings."""
    bookings = list_room_bookings(user_id=user_id)
    conflict = next((item for item in bookings if room_booking_conflicts(request, item)), None)
    if conflict:
        raise HTTPException(
            409,
            f"排练室“{request.room_name}”在 {request.date} {conflict.start}-{conflict.end} 已有预约",
        )
    booking = RoomBooking(booking_id=uuid4().hex, **request.model_dump())
    save_room_booking(booking, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="room",
        operation="create",
        before=bookings,
        after=[*bookings, booking],
    )
    return booking


@router.delete("/resources/rooms/{booking_id}")
def remove_room_booking(booking_id: str, user_id: str = Depends(get_current_user)):
    before = list_room_bookings(user_id=user_id)
    try:
        removed = delete_room_booking(booking_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的预约 ID")
    if not removed:
        raise HTTPException(404, "排练室预约不存在")
    _audit_resource_change(
        user_id=user_id,
        resource_type="room",
        operation="delete",
        before=before,
        after=list_room_bookings(user_id=user_id),
    )
    return {"deleted": True}


@router.get("/resources/music", response_model=list[MusicTimelineNote])
def read_music_timeline(user_id: str = Depends(get_current_user)):
    """Read the current user's music cues and timeline notes."""
    return get_music_notes(user_id=user_id)


@router.put("/resources/music", response_model=list[MusicTimelineNote])
def write_music_timeline(
    request: MusicTimelineUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    ids = [note.note_id for note in request.notes]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "配乐时间轴笔记 ID 不能重复")
    before = get_music_notes(user_id=user_id)
    save_music_notes(request.notes, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="music",
        operation="replace",
        before=before,
        after=request.notes,
    )
    return request.notes


@router.get("/resources/budget", response_model=list[BudgetLineItem])
def read_budget_items(user_id: str = Depends(get_current_user)):
    """Read the current user's budget items."""
    return get_budget_items(user_id=user_id)


@router.put("/resources/budget", response_model=list[BudgetLineItem])
def write_budget_items(
    request: BudgetUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    ids = [item.budget_item_id for item in request.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "预算项目 ID 不能重复")
    before = get_budget_items(user_id=user_id)
    save_budget_items(request.items, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="budget",
        operation="replace",
        before=before,
        after=request.items,
    )
    return request.items


@router.get("/resources/invoices", response_model=list[InvoiceRecord])
def read_resource_invoices(user_id: str = Depends(get_current_user)):
    """Read the current user's invoice metadata."""
    return get_invoices(user_id=user_id)


@router.put("/resources/invoices", response_model=list[InvoiceRecord])
def write_resource_invoices(
    request: InvoiceUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    ids = [invoice.invoice_id for invoice in request.invoices]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "发票 ID 不能重复")
    before = get_invoices(user_id=user_id)
    save_invoices(request.invoices, user_id=user_id)
    _audit_resource_change(
        user_id=user_id,
        resource_type="invoice",
        operation="replace",
        before=before,
        after=request.invoices,
    )
    return request.invoices


@router.get("/resources/finance-summary", response_model=ResourceFinanceSummary)
def read_resource_finance_summary(user_id: str = Depends(get_current_user)):
    """Explain budget, actual spending and invoice linkage for the current user."""
    return ResourceFinanceAgent().summarize(
        get_budget_items(user_id=user_id),
        get_invoices(user_id=user_id),
    )


@router.get("/availability", response_model=list[AvailabilitySlot])
def read_availability(user_id: str = Depends(get_current_user)):
    """Read the user's reusable actor availability pool."""
    return get_availability(user_id=user_id)


@router.put("/availability", response_model=list[AvailabilitySlot])
def write_availability(
    request: AvailabilityUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Persist actor availability independently from any script or schedule."""
    normalized: list[AvailabilitySlot] = []
    seen: set[tuple[str, str, str, str]] = set()
    for slot in request.slots:
        actor = slot.actor.strip()
        key = (actor, slot.date, slot.start, slot.end)
        if not actor or key in seen:
            continue
        seen.add(key)
        normalized.append(slot.model_copy(update={"actor": actor}))
    save_availability(normalized, user_id=user_id)
    return normalized


def _clean_labels(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        label = value.strip()
        if label and label not in result:
            result.append(label)
    return result


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _schedule_trace(draft: ScheduleDraft, *, planned: bool) -> list[AgentStep]:
    """Turn scheduling decisions into a compact, human-readable trace."""
    scheduled = sum(task.status in {"scheduled", "overridden"} for task in draft.tasks)
    overridden = sum(task.status == "overridden" for task in draft.tasks)
    unassigned = [task for task in draft.tasks if task.status == "unassigned"]
    trace = [
        AgentStep(
            name="检查人工确认门槛",
            status="completed",
            summary=(
                "剧本已确认，可生成正式调度。"
                if draft.review_status != "pending"
                else "当前为预览模式，保留人工确认门槛。"
            ),
            output_count=1,
        ),
        AgentStep(
            name="生成场次任务",
            status="completed",
            summary=f"把 {len(draft.tasks)} 个场次转成排练任务。",
            output_count=len(draft.tasks),
        ),
        AgentStep(
            name="识别并行任务组",
            status="completed",
            summary=f"按演员与道具资源冲突分成 {len({task.parallel_group for task in draft.tasks})} 组。",
            output_count=len({task.parallel_group for task in draft.tasks}),
        ),
    ]
    if draft.resource_context is not None:
        trace.append(AgentStep(
            name="读取资源与服装需求上下文",
            status="repaired" if draft.resource_context.warnings else "completed",
            summary=(
                f"读取 {len(draft.resource_context.music_cues)} 个配乐提示点、"
                f"{len(draft.resource_context.budget_items)} 个预算项目、"
                f"{len(draft.resource_context.invoices)} 张发票、"
                f"{len(draft.resource_context.costume_inventory)} 条服装库存、"
                f"{len(draft.resource_context.costume_requirements)} 项剧本服装需求；"
                + ("发现预算超支风险，等待人工确认。" if draft.resource_context.warnings else "未发现预算超支提示。")
            ),
            output_count=(
                len(draft.resource_context.music_cues)
                + len(draft.resource_context.budget_items)
                + len(draft.resource_context.invoices)
                + len(draft.resource_context.costume_inventory)
                + len(draft.resource_context.costume_requirements)
            ),
        ))
    if planned:
        trace.extend([
            AgentStep(
                name="匹配演员可用时间",
                status="completed" if scheduled else "repaired",
                summary=f"完成 {scheduled} 个任务的共同档期匹配。",
                output_count=scheduled,
            ),
            AgentStep(
                name="解释未排班结果",
                status="repaired" if unassigned else "completed",
                summary=(
                    f"有 {len(unassigned)} 个任务保留未排班状态，并写入具体原因。"
                    if unassigned
                    else "所有任务都已找到共同可用时间。"
                ),
                output_count=len(unassigned),
            ),
        ])
        if overridden:
            trace.append(AgentStep(
                name="保留人工覆盖",
                status="completed",
                summary=f"保留 {overridden} 个导演确认的人工覆盖时段，并明确标记为非档期校验结果。",
                output_count=overridden,
            ))
    return trace


def _rebuild_summaries(analysis: ScriptAnalysis) -> None:
    """Recompute downstream scheduling inputs after human metadata edits."""
    characters: dict[str, Character] = {}
    props: dict[str, Prop] = {}
    for scene in analysis.scenes:
        line_characters = {line.character for line in scene.lines}
        for name in _clean_labels([*scene.characters, *line_characters]):
            item = characters.setdefault(name, Character(name=name))
            if scene.scene_id not in item.scene_ids:
                item.scene_ids.append(scene.scene_id)
            item.dialogue_count += sum(line.character == name for line in scene.lines)
        for name in _clean_labels(scene.props):
            item = props.setdefault(name, Prop(name=name))
            if scene.scene_id not in item.scene_ids:
                item.scene_ids.append(scene.scene_id)
            # Human review confirms scene-level usage; exact textual mentions
            # remain available through the original source excerpt.
            item.mention_count += 1
    analysis.characters = list(characters.values())
    analysis.props = list(props.values())
    analysis.costumes = summarize_costume_requirements(analysis.scenes)


def _analyze(
    *,
    title: str,
    version_label: str,
    script_text: str,
    user_id: str,
    source_filename: str | None = None,
    analysis_mode: Literal["auto", "rules", "llm"] = "auto",
):
    started = perf_counter()
    analysis = ScriptAnalysisAgent().run(
        title=title,
        version_label=version_label,
        script_text=script_text,
        script_id=uuid4().hex,
        user_id=user_id,
        analysis_mode=analysis_mode,
    )
    if source_filename:
        analysis.warnings.insert(0, f"来源文件：{source_filename}")
    save_script(analysis, user_id=user_id)
    record_agent_run(
        user_id=user_id,
        agent="script-analysis",
        action="剧本结构化解析",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode=f"{analysis_mode} → {analysis.analysis_mode}",
        status=outcome_status(warnings=analysis.warnings),
        summary=(
            f"识别 {len(analysis.scenes)} 场、{len(analysis.characters)} 个角色、"
            f"{len(analysis.props)} 个道具、{len(analysis.costumes)} 项服装需求和 "
            f"{sum(len(scene.lines) for scene in analysis.scenes)} 句台词。"
        ),
        trace=analysis.trace,
        warnings=analysis.warnings,
        duration_ms=_elapsed_ms(started),
    )
    return analysis


@router.get("/agent-runs", response_model=list[AgentRunRecord])
def read_agent_runs(
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(get_current_user),
):
    """List recent inspectable Agent runs for the current user."""
    return list_agent_runs(user_id=user_id, limit=limit)


@router.get("/agent-runs/metrics", response_model=AgentRunMetricsResponse)
def read_agent_run_metrics(
    window_days: int = Query(default=30, ge=7, le=365),
    user_id: str = Depends(get_current_user),
):
    """Summarize recent run status and failed trace steps for the current user."""
    return AgentRunMetricsAgent().summarize(
        list_agent_runs(user_id=user_id, limit=200),
        window_days=window_days,
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunRecord)
def read_agent_run(run_id: str, user_id: str = Depends(get_current_user)):
    try:
        record = get_agent_run(run_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的 Agent 运行记录 ID")
    if record is None:
        raise HTTPException(404, "Agent 运行记录不存在")
    return record


@router.post("/scripts/parse", response_model=ScriptAnalysis)
async def parse_script(
    request: ScriptParseRequest,
    user_id: str = Depends(get_current_user),
):
    """解析已经读取到内存中的剧本文本，便于前端和测试稳定调用。"""
    return _analyze(
        title=request.title,
        version_label=request.version_label,
        script_text=request.script_text,
        user_id=user_id,
        analysis_mode=request.analysis_mode,
    )


@router.post("/scripts/parse-file", response_model=ScriptAnalysis)
async def parse_script_file(
    file: UploadFile = File(...),
    version_label: str = "v1",
    analysis_mode: Literal["auto", "rules", "llm"] = "auto",
    user_id: str = Depends(get_current_user),
):
    """解析 Markdown、纯文本或可提取文本的 PDF 剧本。"""
    filename = file.filename or "untitled-script.txt"
    suffix = Path(filename).suffix.lower()
    if suffix not in _TEXT_EXTENSIONS and suffix != ".pdf":
        raise HTTPException(400, "当前仅支持 .txt、.md、.markdown 和 .pdf 剧本")

    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "单个剧本不能超过 20 MB")

    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(raw))
        script_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    else:
        try:
            script_text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            script_text = raw.decode("gb18030")

    if not script_text.strip():
        raise HTTPException(400, "剧本内容为空，无法解析")

    return _analyze(
        title=Path(filename).stem,
        version_label=version_label,
        script_text=script_text,
        user_id=user_id,
        source_filename=filename,
        analysis_mode=analysis_mode,
    )


@router.get("/scripts")
def get_scripts(user_id: str = Depends(get_current_user)):
    return {"items": list_scripts(user_id=user_id)}


@router.get("/scripts/{script_id}", response_model=ScriptAnalysis)
def get_script_detail(script_id: str, user_id: str = Depends(get_current_user)):
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    return analysis


@router.post("/scripts/{script_id}/diff", response_model=ScriptVersionDiff)
def compare_script_versions(
    script_id: str,
    request: ScriptDiffRequest,
    user_id: str = Depends(get_current_user),
):
    """Compare the current target script with a saved previous version."""
    try:
        current = get_script(script_id, user_id=user_id)
        previous = get_script(request.compare_script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if current is None:
        raise HTTPException(404, "目标剧本版本不存在")
    if previous is None:
        raise HTTPException(404, "待比较的剧本版本不存在")
    diff = ScriptVersionDiffAgent().compare(previous, current)
    return attach_resource_audit_matches(
        diff,
        list_resource_audits(user_id=user_id, limit=200),
    )


@router.get("/scripts/{script_id}/stage/{scene_id}", response_model=StageVisualization)
def render_stage_visualization(
    script_id: str,
    scene_id: str,
    user_id: str = Depends(get_current_user),
):
    """Render a source-backed stage map and event sequence for one scene."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    try:
        return StageVisualizationAgent().render(analysis, scene_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/scripts/{script_id}/resources/check", response_model=ResourceCheckResponse)
def check_script_resources(
    script_id: str,
    request: ResourceCheckRequest,
    user_id: str = Depends(get_current_user),
):
    """Check script props against the user's current inventory."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    started = perf_counter()
    try:
        response = ResourceAgent().check(
            analysis,
            get_inventory(user_id=user_id),
            scene_id=request.scene_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    record_agent_run(
        user_id=user_id,
        agent="resource-check",
        action="检查排练资源就绪状态",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode="单场" if request.scene_id else "全剧本",
        status=outcome_status(warnings=response.warnings),
        summary=response.summary,
        trace=[
            AgentStep(
                name="读取剧本道具需求",
                status="completed",
                summary=f"读取 {len(response.requirements)} 种待检查道具。",
                output_count=len(response.requirements),
            ),
            AgentStep(
                name="匹配库存状态",
                status="repaired" if response.warnings else "completed",
                summary=f"得到 {response.ready_count} 种已就绪、{response.missing_count} 种仍需处理的结果。",
                output_count=len(response.requirements),
            ),
            AgentStep(
                name="解释资源缺口",
                status="completed",
                summary=response.summary,
                output_count=len(response.warnings),
            ),
        ],
        warnings=response.warnings,
        duration_ms=_elapsed_ms(started),
    )
    return response


@router.post("/scripts/{script_id}/rag", response_model=ScriptRagResponse)
def query_script_rag(
    script_id: str,
    request: ScriptRagQueryRequest,
    user_id: str = Depends(get_current_user),
):
    """Answer a script question with inspectable scene and source-line evidence."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    started = perf_counter()
    response = ScriptRagAgent().answer(analysis, request, user_id=user_id)
    warnings: list[str] = []
    if response.retrieval_engine == "rules-fallback":
        warnings.append("语义检索不可用，已回退到规则检索。")
    if response.engine == "fallback":
        warnings.append(response.note)
    trace = [
        AgentStep(
            name="构建剧本证据块",
            status="completed",
            summary=f"从 {len(analysis.scenes)} 个场次构建可回指的场景、台词和舞台提示。",
            output_count=len(analysis.scenes),
        ),
        AgentStep(
            name="检索相关证据",
            status="repaired" if response.retrieval_engine == "rules-fallback" else "completed",
            summary=f"使用 {response.retrieval_engine} 检索，返回 {len(response.evidence)} 条证据。",
            output_count=len(response.evidence),
        ),
        AgentStep(
            name="组织带引用回答",
            status="repaired" if response.engine == "fallback" else "completed",
            summary=f"使用 {response.engine} 生成回答，并保留证据 ID。",
            output_count=1 if response.answer else 0,
        ),
    ]
    record_agent_run(
        user_id=user_id,
        agent="script-rag",
        action="剧本证据问答",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode=f"检索:{request.retrieval_mode} / 回答:{request.answer_mode}",
        status=("fallback" if warnings else "completed"),
        summary=f"围绕“{request.question}”返回 {len(response.evidence)} 条可核对证据。",
        trace=trace,
        warnings=warnings,
        duration_ms=_elapsed_ms(started),
    )
    return response


@router.put("/scripts/{script_id}/review", response_model=ScriptAnalysis)
def review_script(
    script_id: str,
    request: ScriptReviewRequest,
    user_id: str = Depends(get_current_user),
):
    """Persist human-in-the-loop confirmation for one parsed script.

    Only scene metadata is editable in this milestone. Original dialogue and
    source spans stay server-side so downstream scheduling can trust its evidence.
    """
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")

    existing_ids = [scene.scene_id for scene in analysis.scenes]
    incoming_ids = [scene.scene_id for scene in request.scenes]
    if len(incoming_ids) != len(set(incoming_ids)) or set(incoming_ids) != set(existing_ids):
        raise HTTPException(400, "审核结果中的场次必须与原解析结果完全一致")

    updates = {scene.scene_id: scene for scene in request.scenes}
    for scene in analysis.scenes:
        patch = updates[scene.scene_id]
        scene.title = patch.title.strip()
        scene.characters = _clean_labels(patch.characters)
        scene.props = _clean_labels(patch.props)
        scene.costumes = _clean_labels(patch.costumes)

    _rebuild_summaries(analysis)
    analysis.review_status = request.review_status
    analysis.reviewed_at = datetime.now(timezone.utc).isoformat()
    analysis.review_note = request.review_note.strip()
    delete_schedule(script_id, user_id=user_id)
    save_script(analysis, user_id=user_id)
    return analysis


@router.post("/scripts/{script_id}/schedule/draft", response_model=ScheduleDraft)
def create_schedule_draft(
    script_id: str,
    request: ScheduleDraftRequest,
    user_id: str = Depends(get_current_user),
):
    """Create a formal draft or an explicitly marked pre-review preview."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    started = perf_counter()
    run_id = uuid4().hex
    try:
        draft = RehearsalScheduleAgent().run(
            analysis,
            default_minutes=request.default_minutes,
            costume_changeover_minutes=request.costume_changeover_minutes,
            preview=request.preview,
            agent_run_id=run_id,
            root_run_id=run_id,
            music_notes=get_music_notes(user_id=user_id),
            budget_items=get_budget_items(user_id=user_id),
            invoices=get_invoices(user_id=user_id),
            inventory=get_inventory(user_id=user_id),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    save_schedule(draft, user_id=user_id)
    record_agent_run(
        user_id=user_id,
        agent="schedule-draft",
        action="生成排练调度草案",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode="预览" if request.preview else "正式",
        summary=f"生成 {len(draft.tasks)} 个场次任务，划分 {len({task.parallel_group for task in draft.tasks})} 个并行组。",
        trace=_schedule_trace(draft, planned=False),
        warnings=list(draft.resource_context.warnings) if draft.resource_context else [],
        duration_ms=_elapsed_ms(started),
        run_id=run_id,
        root_run_id=run_id,
    )
    return draft


@router.get("/scripts/{script_id}/schedule", response_model=ScheduleDraft)
def get_schedule_draft(script_id: str, user_id: str = Depends(get_current_user)):
    try:
        draft = get_schedule(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if draft is None:
        raise HTTPException(404, "排练调度草案不存在")
    return draft


@router.post("/scripts/{script_id}/schedule/plan", response_model=ScheduleDraft)
def plan_schedule(
    script_id: str,
    request: SchedulePlanRequest,
    user_id: str = Depends(get_current_user),
):
    """Assign the draft tasks to actor availability intersections."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    started = perf_counter()
    plan_run_id = uuid4().hex
    try:
        draft = get_schedule(script_id, user_id=user_id)
        if draft is None:
            draft_run_id = uuid4().hex
            draft = RehearsalScheduleAgent().run(
                analysis,
                agent_run_id=draft_run_id,
                root_run_id=draft_run_id,
                music_notes=get_music_notes(user_id=user_id),
                budget_items=get_budget_items(user_id=user_id),
                invoices=get_invoices(user_id=user_id),
                inventory=get_inventory(user_id=user_id),
            )
            save_schedule(draft, user_id=user_id)
            record_agent_run(
                user_id=user_id,
                agent="schedule-draft",
                action="补生成排练调度草案",
                script_id=analysis.script_id,
                script_title=analysis.title,
                mode="自动排班前补生成",
                summary=f"为自动排班补生成 {len(draft.tasks)} 个场次任务。",
                trace=_schedule_trace(draft, planned=False),
                warnings=list(draft.resource_context.warnings) if draft.resource_context else [],
                duration_ms=0,
                run_id=draft_run_id,
                root_run_id=draft_run_id,
            )
        parent_run_id = draft.agent_run_id
        root_run_id = draft.root_run_id or parent_run_id or plan_run_id
        planned = RehearsalScheduleAgent().assign(
            draft,
            request.slots,
            agent_run_id=plan_run_id,
            parent_run_id=parent_run_id,
            root_run_id=root_run_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    save_schedule(planned, user_id=user_id)
    unassigned = [task for task in planned.tasks if task.status == "unassigned"]
    record_agent_run(
        user_id=user_id,
        agent="schedule-plan",
        action="匹配演员档期",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode="共同空闲时间匹配",
        summary=(
            f"已排 {len(planned.tasks) - len(unassigned)} 个任务；"
            f"{len(unassigned)} 个任务保留未排班及原因。"
        ),
        trace=_schedule_trace(planned, planned=True),
        warnings=[
            *([*planned.resource_context.warnings] if planned.resource_context else []),
            *[task.unassigned_reason or "" for task in unassigned],
        ],
        duration_ms=_elapsed_ms(started),
        run_id=plan_run_id,
        parent_run_id=planned.parent_run_id,
        root_run_id=planned.root_run_id,
    )
    return planned


@router.post("/scripts/{script_id}/schedule/override", response_model=ScheduleDraft)
def override_schedule(
    script_id: str,
    request: ScheduleOverrideRequest,
    user_id: str = Depends(get_current_user),
):
    """Apply an explicit director override while keeping the decision auditable."""
    try:
        analysis = get_script(script_id, user_id=user_id)
        draft = get_schedule(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本或调度 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    if draft is None:
        raise HTTPException(404, "排练调度草案不存在")
    started = perf_counter()
    run_id = uuid4().hex
    try:
        updated = RehearsalScheduleAgent().apply_manual_override(
            draft,
            task_id=request.task_id,
            date=request.date,
            start=request.start,
            end=request.end,
            room_name=request.room_name,
            note=request.note,
            room_bookings=list_room_bookings(user_id=user_id),
            agent_run_id=run_id,
            parent_run_id=draft.agent_run_id,
            root_run_id=draft.root_run_id or draft.agent_run_id or run_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    save_schedule(updated, user_id=user_id)
    overridden = next(task for task in updated.tasks if task.task_id == request.task_id)
    record_agent_run(
        user_id=user_id,
        agent="schedule-plan",
        action="人工覆盖排班",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode="导演人工确认",
        summary=f"第 {overridden.scene_number} 场已由导演确认人工覆盖时段。",
        trace=_schedule_trace(updated, planned=True),
        warnings=[overridden.manual_override.note] if overridden.manual_override else [],
        duration_ms=_elapsed_ms(started),
        run_id=run_id,
        parent_run_id=updated.parent_run_id,
        root_run_id=updated.root_run_id,
    )
    return updated


@router.post("/scripts/{script_id}/schedule/override-batch", response_model=ScheduleBatchOverrideResponse)
def override_schedule_batch(
    script_id: str,
    request: ScheduleBatchOverrideRequest,
    user_id: str = Depends(get_current_user),
):
    """Confirm several director-selected schedule slots as one atomic action."""
    try:
        analysis = get_script(script_id, user_id=user_id)
        draft = get_schedule(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本或调度 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    if draft is None:
        raise HTTPException(404, "排练调度草案不存在")
    started = perf_counter()
    run_id = uuid4().hex
    try:
        updated = RehearsalScheduleAgent().apply_manual_overrides(
            draft,
            request.overrides,
            room_bookings=list_room_bookings(user_id=user_id),
            agent_run_id=run_id,
            parent_run_id=draft.agent_run_id,
            root_run_id=draft.root_run_id or draft.agent_run_id or run_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    save_schedule(updated, user_id=user_id)
    confirmed_task_ids = [item.task_id for item in request.overrides]
    record_agent_run(
        user_id=user_id,
        agent="schedule-plan",
        action="批量人工确认排班",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode="导演批量确认",
        summary=f"导演一次确认 {len(confirmed_task_ids)} 个排练任务。",
        trace=_schedule_trace(updated, planned=True),
        warnings=[],
        duration_ms=_elapsed_ms(started),
        run_id=run_id,
        parent_run_id=updated.parent_run_id,
        root_run_id=updated.root_run_id,
    )
    return ScheduleBatchOverrideResponse(
        script_id=analysis.script_id,
        schedule=updated,
        confirmed_task_ids=confirmed_task_ids,
        overridden_count=len(confirmed_task_ids),
        atomic=True,
    )


@router.post("/scripts/{script_id}/line-reading", response_model=LineReadingResponse)
def line_reading(
    script_id: str,
    request: LineReadingRequest,
    user_id: str = Depends(get_current_user),
):
    """Advance one role-play turn while keeping the stored script as evidence."""
    try:
        analysis = get_script(script_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的剧本 ID")
    if analysis is None:
        raise HTTPException(404, "剧本解析结果不存在")
    started = perf_counter()
    try:
        session = get_line_reading_session(request.session_id, user_id=user_id) if request.session_id else None
        if request.session_id and session is None:
            raise ValueError("对词会话不存在，请重新开始当前场次")
        response, updated_session = LineReadingSessionAgent().advance(
            analysis,
            request,
            session=session,
            user_id=user_id,
        )
        save_line_reading_session(updated_session, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    warnings = [response.note] if response.engine == "fallback" and response.note else []
    record_agent_run(
        user_id=user_id,
        agent="line-reading",
        action="推进角色对词",
        script_id=analysis.script_id,
        script_title=analysis.title,
        mode=request.mode,
        status=outcome_status(engine=response.engine, warnings=warnings),
        summary=(
            f"为角色“{response.character}”推进到第 {response.next_line_index + 1 if response.next_line_index is not None else '末句'} 个台词位置，"
            f"返回 {len(response.assistant_turns)} 个搭词提示。"
        ),
        trace=[
            AgentStep(
                name="校验角色与场次",
                status="completed",
                summary=f"确认角色“{response.character}”属于《{response.scene_title}》当前场次。",
                output_count=1,
            ),
            AgentStep(
                name="选择对词策略",
                status="repaired" if response.engine == "fallback" else "completed",
                summary=f"使用 {response.mode} 模式和 {response.engine} 引擎推进对话。",
                output_count=len(response.assistant_turns),
            ),
            AgentStep(
                name="回指下一句原台词",
                status="completed",
                summary=(
                    f"下一句台词位于原剧本第 {response.actor_prompt.source_line} 行。"
                    if response.actor_prompt
                    else "当前场次对词已完成。"
                ),
                output_count=1 if response.actor_prompt else 0,
            ),
        ],
        warnings=warnings,
        duration_ms=_elapsed_ms(started),
    )
    return response


@router.get("/scripts/{script_id}/line-reading/sessions/{session_id}", response_model=LineReadingSession)
def read_line_reading_session(
    script_id: str,
    session_id: str,
    user_id: str = Depends(get_current_user),
):
    """Resume a user-scoped line-reading cursor and transcript."""
    try:
        session = get_line_reading_session(session_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的对词会话 ID")
    if session is None or session.script_id != script_id:
        raise HTTPException(404, "对词会话不存在")
    return session


@router.post("/feedback", response_model=RehearsalFeedbackResponse)
def create_rehearsal_feedback(
    request: RehearsalFeedbackRequest,
    user_id: str = Depends(get_current_user),
):
    """Archive raw rehearsal notes and return the structured mirror."""
    analysis = None
    script_title = ""
    scene_title = ""
    if request.script_id:
        try:
            analysis = get_script(request.script_id, user_id=user_id)
        except ValueError:
            raise HTTPException(400, "无效的剧本 ID")
        if analysis is None:
            raise HTTPException(404, "关联剧本不存在")
        script_title = analysis.title
        if request.scene_id:
            scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
            if scene is None:
                raise HTTPException(400, "关联场次不存在")
            scene_title = scene.title
    elif request.scene_id:
        raise HTTPException(400, "指定场次时必须同时指定剧本")

    record = RehearsalMirrorAgent().summarize(
        request,
        record_id=uuid4().hex,
        script_title=script_title,
        scene_title=scene_title,
        user_id=user_id,
    )
    save_feedback(record, user_id=user_id)
    return record


@router.get("/feedback", response_model=list[RehearsalFeedbackResponse])
def read_rehearsal_feedback(user_id: str = Depends(get_current_user)):
    """Read the current user's rehearsal mirror archive."""
    return list_feedback(user_id=user_id)


@router.get("/feedback/metrics", response_model=RehearsalMetricsResponse)
def read_rehearsal_metrics(
    days: int = Query(default=30, ge=7, le=365),
    user_id: str = Depends(get_current_user),
):
    """Summarize the current user's archived feedback for the selected window."""
    return RehearsalMetricsAgent().summarize(list_feedback(user_id=user_id), window_days=days)


@router.get("/feedback/{record_id}", response_model=RehearsalFeedbackResponse)
def read_rehearsal_feedback_detail(record_id: str, user_id: str = Depends(get_current_user)):
    try:
        record = get_feedback(record_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的反馈记录 ID")
    if record is None:
        raise HTTPException(404, "排练反馈记录不存在")
    return record


@router.post("/logbook", response_model=RehearsalLogResponse)
def create_rehearsal_log(
    request: RehearsalLogRequest,
    user_id: str = Depends(get_current_user),
):
    """Archive one stage-management note with optional script evidence."""
    script_title = ""
    scene_title = ""
    if request.script_id:
        try:
            analysis = get_script(request.script_id, user_id=user_id)
        except ValueError:
            raise HTTPException(400, "无效的剧本 ID")
        if analysis is None:
            raise HTTPException(404, "关联剧本不存在")
        script_title = analysis.title
        if request.scene_id:
            scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
            if scene is None:
                raise HTTPException(400, "关联场次不存在")
            scene_title = scene.title
    elif request.scene_id:
        raise HTTPException(400, "指定场次时必须同时指定剧本")

    record = RehearsalLogAgent().record(
        request,
        log_id=uuid4().hex,
        script_title=script_title,
        scene_title=scene_title,
    )
    save_log(record, user_id=user_id)
    return record


@router.get("/logbook", response_model=list[RehearsalLogResponse])
def read_rehearsal_logs(user_id: str = Depends(get_current_user)):
    return list_logs(user_id=user_id)


@router.delete("/logbook/{log_id}")
def remove_rehearsal_log(log_id: str, user_id: str = Depends(get_current_user)):
    try:
        removed = delete_log(log_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的场记记录 ID")
    if not removed:
        raise HTTPException(404, "场记记录不存在")
    return {"deleted": True}


@router.post("/suggestions", response_model=SuggestionResponse)
def create_suggestion(
    request: SuggestionRequest,
    user_id: str = Depends(get_current_user),
):
    """Submit an actor suggestion with optional script context."""
    script_title = ""
    scene_title = ""
    if request.script_id:
        try:
            analysis = get_script(request.script_id, user_id=user_id)
        except ValueError:
            raise HTTPException(400, "无效的剧本 ID")
        if analysis is None:
            raise HTTPException(404, "关联剧本不存在")
        script_title = analysis.title
        if request.scene_id:
            scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
            if scene is None:
                raise HTTPException(400, "关联场次不存在")
            scene_title = scene.title
    elif request.scene_id:
        raise HTTPException(400, "指定场次时必须同时指定剧本")

    suggestion = SuggestionInboxAgent().submit(
        request,
        suggestion_id=uuid4().hex,
        script_title=script_title,
        scene_title=scene_title,
    )
    save_suggestion(suggestion, user_id=user_id)
    return suggestion


@router.get("/suggestions", response_model=list[SuggestionResponse])
def read_suggestions(user_id: str = Depends(get_current_user)):
    return list_suggestions(user_id=user_id)


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionResponse)
def update_suggestion(
    suggestion_id: str,
    request: SuggestionUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    try:
        suggestion = get_suggestion(suggestion_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的建议 ID")
    if suggestion is None:
        raise HTTPException(404, "建议记录不存在")
    updated = SuggestionInboxAgent().update(suggestion, request)
    save_suggestion(updated, user_id=user_id)
    return updated


@router.delete("/suggestions/{suggestion_id}")
def remove_suggestion(suggestion_id: str, user_id: str = Depends(get_current_user)):
    try:
        removed = delete_suggestion(suggestion_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的建议 ID")
    if not removed:
        raise HTTPException(404, "建议记录不存在")
    return {"deleted": True}


@router.post("/knowledge/mottos", response_model=MottoResponse)
def create_motto(
    request: MottoRequest,
    user_id: str = Depends(get_current_user),
):
    """Archive a quote with optional script context."""
    script_title = ""
    scene_title = ""
    if request.script_id:
        try:
            analysis = get_script(request.script_id, user_id=user_id)
        except ValueError:
            raise HTTPException(400, "无效的剧本 ID")
        if analysis is None:
            raise HTTPException(404, "关联剧本不存在")
        script_title = analysis.title
        if request.scene_id:
            scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
            if scene is None:
                raise HTTPException(400, "关联场次不存在")
            scene_title = scene.title
    elif request.scene_id:
        raise HTTPException(400, "指定场次时必须同时指定剧本")

    motto = MottoAgent().record(
        request,
        motto_id=uuid4().hex,
        script_title=script_title,
        scene_title=scene_title,
    )
    save_motto(motto, user_id=user_id)
    return motto


@router.get("/knowledge/mottos", response_model=list[MottoResponse])
def read_mottos(user_id: str = Depends(get_current_user)):
    return list_mottos(user_id=user_id)


@router.patch("/knowledge/mottos/{motto_id}", response_model=MottoResponse)
def update_motto(
    motto_id: str,
    request: MottoUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    try:
        motto = get_motto(motto_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的格言 ID")
    if motto is None:
        raise HTTPException(404, "格言记录不存在")
    updated = MottoAgent().update(motto, request)
    save_motto(updated, user_id=user_id)
    return updated


@router.delete("/knowledge/mottos/{motto_id}")
def remove_motto(motto_id: str, user_id: str = Depends(get_current_user)):
    try:
        removed = delete_motto(motto_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的格言 ID")
    if not removed:
        raise HTTPException(404, "格言记录不存在")
    return {"deleted": True}


@router.post("/knowledge/promo", response_model=PromoCopyResponse)
def create_promo_copy(
    request: PromoCopyRequest,
    user_id: str = Depends(get_current_user),
):
    """Generate and archive publicity copy from saved script structure or a brief."""
    script_title = ""
    scene_titles: list[str] = []
    characters: list[str] = []
    if request.script_id:
        try:
            analysis = get_script(request.script_id, user_id=user_id)
        except ValueError:
            raise HTTPException(400, "无效的剧本 ID")
        if analysis is None:
            raise HTTPException(404, "关联剧本不存在")
        script_title = analysis.title
        scene_titles = [scene.title for scene in analysis.scenes]
        characters = [character.name for character in analysis.characters]

    copy = PromoCopyAgent().generate(
        request,
        copy_id=uuid4().hex,
        script_title=script_title,
        scene_titles=scene_titles,
        characters=characters,
        user_id=user_id,
    )
    save_promo_copy(copy, user_id=user_id)
    return copy


@router.get("/knowledge/promo", response_model=list[PromoCopyResponse])
def read_promo_copies(user_id: str = Depends(get_current_user)):
    return list_promo_copies(user_id=user_id)
