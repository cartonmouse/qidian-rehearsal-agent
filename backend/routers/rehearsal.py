"""奇点剧团排练领域 API。"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pypdf import PdfReader

from backend.auth import get_current_user
from backend.rehearsal.agent import ScriptAnalysisAgent
from backend.rehearsal.feedback_agent import RehearsalMirrorAgent
from backend.rehearsal.finance_agent import ResourceFinanceAgent
from backend.rehearsal.line_reading import LineReadingAgent
from backend.rehearsal.logbook_agent import RehearsalLogAgent
from backend.rehearsal.metrics_agent import RehearsalMetricsAgent
from backend.rehearsal.motto_agent import MottoAgent
from backend.rehearsal.promo_agent import PromoCopyAgent
from backend.rehearsal.rag_agent import ScriptRagAgent
from backend.rehearsal.resource_agent import ResourceAgent, room_booking_conflicts
from backend.rehearsal.schedule_agent import RehearsalScheduleAgent
from backend.rehearsal.stage_agent import StageVisualizationAgent
from backend.rehearsal.suggestion_agent import SuggestionInboxAgent
from backend.rehearsal.version_diff import ScriptVersionDiffAgent
from backend.rehearsal.models import (
    AvailabilitySlot,
    AvailabilityUpdateRequest,
    BudgetLineItem,
    BudgetUpdateRequest,
    Character,
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
    ResourceInventoryItem,
    ResourceInventoryUpdateRequest,
    ResourceFinanceSummary,
    RoomBooking,
    RoomBookingRequest,
    ScriptDiffRequest,
    StageVisualization,
    ScriptVersionDiff,
    ScheduleDraft,
    ScheduleDraftRequest,
    SchedulePlanRequest,
    ScriptAnalysis,
    LineReadingRequest,
    LineReadingResponse,
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
    get_budget_items,
    get_feedback,
    get_inventory,
    get_invoices,
    get_motto,
    get_music_notes,
    get_schedule,
    get_script,
    get_suggestion,
    list_feedback,
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
    save_music_notes,
    delete_room_booking,
    delete_log,
    save_suggestion,
    delete_suggestion,
    save_motto,
    delete_motto,
    save_promo_copy,
)


router = APIRouter(prefix="/api/rehearsal", tags=["rehearsal"])
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


@router.get("/resources/inventory", response_model=list[ResourceInventoryItem])
def read_resource_inventory(user_id: str = Depends(get_current_user)):
    """Read the current user's prop and costume inventory."""
    return get_inventory(user_id=user_id)


@router.put("/resources/inventory", response_model=list[ResourceInventoryItem])
def write_resource_inventory(
    request: ResourceInventoryUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    """Replace the current user's inventory in one explicit, reviewable action."""
    ids = [item.resource_id for item in request.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "资源记录 ID 不能重复")
    save_inventory(request.items, user_id=user_id)
    return request.items


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
    return booking


@router.delete("/resources/rooms/{booking_id}")
def remove_room_booking(booking_id: str, user_id: str = Depends(get_current_user)):
    try:
        removed = delete_room_booking(booking_id, user_id=user_id)
    except ValueError:
        raise HTTPException(400, "无效的预约 ID")
    if not removed:
        raise HTTPException(404, "排练室预约不存在")
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
    save_music_notes(request.notes, user_id=user_id)
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
    save_budget_items(request.items, user_id=user_id)
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
    save_invoices(request.invoices, user_id=user_id)
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


def _analyze(
    *,
    title: str,
    version_label: str,
    script_text: str,
    user_id: str,
    source_filename: str | None = None,
    analysis_mode: Literal["auto", "rules", "llm"] = "auto",
):
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
    return analysis


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
    return ScriptVersionDiffAgent().compare(previous, current)


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
    try:
        return ResourceAgent().check(
            analysis,
            get_inventory(user_id=user_id),
            scene_id=request.scene_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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
    return ScriptRagAgent().answer(analysis, request, user_id=user_id)


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
    try:
        draft = RehearsalScheduleAgent().run(
            analysis,
            default_minutes=request.default_minutes,
            preview=request.preview,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    save_schedule(draft, user_id=user_id)
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
    try:
        draft = get_schedule(script_id, user_id=user_id)
        if draft is None:
            draft = RehearsalScheduleAgent().run(analysis)
        planned = RehearsalScheduleAgent().assign(draft, request.slots)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    save_schedule(planned, user_id=user_id)
    return planned


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
    try:
        return LineReadingAgent().respond(analysis, request, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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
