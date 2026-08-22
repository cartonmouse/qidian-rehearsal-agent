"""剧本解析 Agent 的领域模型与 API 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceSpan(BaseModel):
    """结构化产出回指原剧本的位置，便于人工核对。"""

    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str = ""


class DialogueLine(BaseModel):
    line_id: str
    character: str
    text: str
    source: SourceSpan


class StageDirection(BaseModel):
    text: str
    kind: Literal["entrance", "exit", "movement", "prop", "other"] = "other"
    source_line: int = Field(ge=1)


class Scene(BaseModel):
    scene_id: str
    number: int = Field(ge=1)
    title: str
    characters: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    lines: list[DialogueLine] = Field(default_factory=list)
    stage_directions: list[StageDirection] = Field(default_factory=list)
    source: SourceSpan


class Character(BaseModel):
    name: str
    scene_ids: list[str] = Field(default_factory=list)
    dialogue_count: int = Field(default=0, ge=0)


class Prop(BaseModel):
    name: str
    scene_ids: list[str] = Field(default_factory=list)
    mention_count: int = Field(default=0, ge=0)


class AgentStep(BaseModel):
    name: str
    status: Literal["completed", "repaired", "failed"]
    summary: str
    output_count: int = Field(default=0, ge=0)


class AgentRunRecord(BaseModel):
    """A persisted, user-scoped run summary for an inspectable rehearsal Agent."""

    run_id: str
    parent_run_id: str | None = None
    root_run_id: str | None = None
    agent: Literal["script-analysis", "schedule-draft", "schedule-plan", "line-reading", "script-rag", "resource-check"]
    action: str
    script_id: str | None = None
    script_title: str = ""
    mode: str = ""
    status: Literal["completed", "fallback", "failed"] = "completed"
    summary: str
    trace: list[AgentStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    created_at: str


class AgentRunMetricItem(BaseModel):
    agent: str
    run_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    failure_rate: float = Field(ge=0, le=100)
    fallback_rate: float = Field(ge=0, le=100)
    average_duration_ms: int = Field(default=0, ge=0)


class AgentFailureStep(BaseModel):
    name: str
    failed_count: int = Field(ge=0)
    last_summary: str = ""


class AgentRunMetricsResponse(BaseModel):
    window_days: int = Field(ge=7, le=365)
    from_datetime: str
    to_datetime: str
    total_runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    fallback_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    failure_rate: float = Field(ge=0, le=100)
    fallback_rate: float = Field(ge=0, le=100)
    average_duration_ms: int = Field(default=0, ge=0)
    by_agent: list[AgentRunMetricItem] = Field(default_factory=list)
    failed_steps: list[AgentFailureStep] = Field(default_factory=list)
    note: str = ""
    generated_at: str


class ScriptParseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    version_label: str = Field(default="v1", min_length=1, max_length=50)
    script_text: str = Field(min_length=1, max_length=500_000)
    analysis_mode: Literal["auto", "rules", "llm"] = "auto"


class SceneReviewPatch(BaseModel):
    """Human-editable scene metadata; source spans and dialogue remain immutable."""

    scene_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    characters: list[str] = Field(default_factory=list, max_length=100)
    props: list[str] = Field(default_factory=list, max_length=100)


class ScriptReviewRequest(BaseModel):
    scenes: list[SceneReviewPatch] = Field(min_length=1, max_length=200)
    review_status: Literal["confirmed", "edited"] = "confirmed"
    review_note: str = Field(default="", max_length=2_000)


class ScheduleDraftRequest(BaseModel):
    default_minutes: int = Field(default=45, ge=15, le=180)
    preview: bool = False


class AvailabilitySlot(BaseModel):
    actor: str = Field(min_length=1, max_length=100)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("actor")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("演员姓名不能为空")
        return value

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("日期必须是有效的 YYYY-MM-DD") from exc
        return value

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        hour, minute = (int(part) for part in value.split(":", 1))
        if hour > 23 or minute > 59:
            raise ValueError("时间必须是有效的 HH:MM")
        return value

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start >= self.end:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class SchedulePlanRequest(BaseModel):
    slots: list[AvailabilitySlot] = Field(min_length=1, max_length=500)


class ScheduleOverrideRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    note: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("日期必须是有效的 YYYY-MM-DD") from exc
        return value

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        hour, minute = (int(part) for part in value.split(":", 1))
        if hour > 23 or minute > 59:
            raise ValueError("时间必须是有效的 HH:MM")
        return value

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start >= self.end:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class ScheduleBatchOverrideRequest(BaseModel):
    """A single atomic director confirmation for several schedule tasks."""

    overrides: list[ScheduleOverrideRequest] = Field(min_length=1, max_length=200)


class AvailabilityUpdateRequest(BaseModel):
    """User-level actor availability that can be maintained before a script exists."""

    slots: list[AvailabilitySlot] = Field(default_factory=list, max_length=500)


class ResourceInventoryItem(BaseModel):
    """A user-maintained prop or costume inventory record."""

    resource_id: str = Field(default_factory=lambda: uuid4().hex)
    category: Literal["prop", "costume"]
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=0, le=10_000)
    status: Literal["available", "maintenance", "missing"] = "available"
    location: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2_000)

    @field_validator("name", "location", "notes")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("资源名称不能为空")
        return value


class ResourceInventoryUpdateRequest(BaseModel):
    items: list[ResourceInventoryItem] = Field(default_factory=list, max_length=1_000)


class ResourceAuditChange(BaseModel):
    change_type: Literal["created", "updated", "deleted"]
    resource_id: str
    label: str
    changed_fields: list[str] = Field(default_factory=list)
    summary: str


class ResourceAuditRecord(BaseModel):
    audit_id: str
    resource_type: Literal["inventory", "room", "music", "budget", "invoice"]
    operation: Literal["replace", "create", "delete"]
    changed_count: int = Field(ge=0)
    changes: list[ResourceAuditChange] = Field(default_factory=list)
    summary: str
    created_at: str


class VersionResourceAuditMatch(BaseModel):
    """A user-scoped resource change matched to a changed script prop."""

    audit_id: str
    resource_type: Literal["inventory", "room", "music", "budget", "invoice"]
    change_type: Literal["created", "updated", "deleted"]
    resource_id: str
    label: str
    summary: str
    created_at: str


class RoomBookingRequest(BaseModel):
    room_name: str = Field(min_length=1, max_length=200)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    purpose: str = Field(default="排练", max_length=500)

    @field_validator("room_name", "purpose")
    @classmethod
    def normalize_booking_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("room_name")
    @classmethod
    def validate_room_name(cls, value: str) -> str:
        if not value:
            raise ValueError("排练室名称不能为空")
        return value

    @field_validator("date")
    @classmethod
    def validate_booking_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("预约日期必须是有效的 YYYY-MM-DD") from exc
        return value

    @field_validator("start", "end")
    @classmethod
    def validate_booking_time(cls, value: str) -> str:
        hour, minute = (int(part) for part in value.split(":", 1))
        if hour > 23 or minute > 59:
            raise ValueError("预约时间必须是有效的 HH:MM")
        return value

    @model_validator(mode="after")
    def validate_booking_interval(self):
        if self.start >= self.end:
            raise ValueError("排练室结束时间必须晚于开始时间")
        return self


class RoomBooking(RoomBookingRequest):
    booking_id: str = Field(default_factory=lambda: uuid4().hex)


class MusicTimelineNoteRequest(BaseModel):
    """A cue or note on the rehearsal music timeline."""

    track_name: str = Field(min_length=1, max_length=200)
    scene_id: str | None = Field(default=None, max_length=100)
    cue_type: Literal["intro", "cue", "transition", "outro", "other"] = "cue"
    start_seconds: int = Field(default=0, ge=0, le=86_400)
    end_seconds: int | None = Field(default=None, ge=0, le=86_400)
    note: str = Field(default="", max_length=2_000)

    @field_validator("track_name", "scene_id", "note")
    @classmethod
    def normalize_music_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("track_name")
    @classmethod
    def validate_track_name(cls, value: str) -> str:
        if not value:
            raise ValueError("配乐名称不能为空")
        return value

    @model_validator(mode="after")
    def validate_music_interval(self):
        if self.end_seconds is not None and self.end_seconds < self.start_seconds:
            raise ValueError("配乐结束时间不能早于开始时间")
        return self


class MusicTimelineNote(MusicTimelineNoteRequest):
    note_id: str = Field(default_factory=lambda: uuid4().hex)


class MusicTimelineUpdateRequest(BaseModel):
    notes: list[MusicTimelineNote] = Field(default_factory=list, max_length=1_000)


class BudgetLineItemRequest(BaseModel):
    """One planned or actual spending item for the production."""

    category: Literal["prop", "costume", "music", "room", "transport", "promotion", "other"] = "other"
    name: str = Field(min_length=1, max_length=200)
    estimated_amount: float = Field(default=0, ge=0, le=100_000_000)
    actual_amount: float = Field(default=0, ge=0, le=100_000_000)
    status: Literal["planned", "committed", "paid", "cancelled"] = "planned"
    note: str = Field(default="", max_length=2_000)

    @field_validator("name", "note")
    @classmethod
    def normalize_budget_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_budget_name(cls, value: str) -> str:
        if not value:
            raise ValueError("预算项目名称不能为空")
        return value


class BudgetLineItem(BudgetLineItemRequest):
    budget_item_id: str = Field(default_factory=lambda: uuid4().hex)


class BudgetUpdateRequest(BaseModel):
    items: list[BudgetLineItem] = Field(default_factory=list, max_length=1_000)


class InvoiceRecordRequest(BaseModel):
    """Metadata for a receipt/invoice; the file itself stays outside the API MVP."""

    invoice_no: str = Field(default="", max_length=200)
    supplier: str = Field(min_length=1, max_length=200)
    invoice_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: Literal["prop", "costume", "music", "room", "transport", "promotion", "other"] = "other"
    amount: float = Field(ge=0, le=100_000_000)
    budget_item_id: str | None = Field(default=None, max_length=100)
    status: Literal["pending", "verified", "paid", "rejected"] = "pending"
    note: str = Field(default="", max_length=2_000)

    @field_validator("invoice_no", "supplier", "budget_item_id", "note")
    @classmethod
    def normalize_invoice_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("supplier")
    @classmethod
    def validate_supplier(cls, value: str) -> str:
        if not value:
            raise ValueError("发票供应商不能为空")
        return value

    @field_validator("invoice_date")
    @classmethod
    def validate_invoice_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("发票日期必须是有效的 YYYY-MM-DD") from exc
        return value


class InvoiceRecord(InvoiceRecordRequest):
    invoice_id: str = Field(default_factory=lambda: uuid4().hex)


class InvoiceUpdateRequest(BaseModel):
    invoices: list[InvoiceRecord] = Field(default_factory=list, max_length=1_000)


class BudgetCategorySummary(BaseModel):
    category: str
    estimated_amount: float = Field(ge=0)
    actual_amount: float = Field(ge=0)
    invoice_amount: float = Field(ge=0)


class ResourceFinanceSummary(BaseModel):
    estimated_total: float = Field(ge=0)
    actual_total: float = Field(ge=0)
    invoice_total: float = Field(ge=0)
    verified_invoice_total: float = Field(ge=0)
    linked_invoice_total: float = Field(ge=0)
    unlinked_invoice_total: float = Field(ge=0)
    variance: float
    categories: list[BudgetCategorySummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    note: str = ""


class ResourceCheckRequest(BaseModel):
    scene_id: str | None = Field(default=None, max_length=100)

    @field_validator("scene_id")
    @classmethod
    def normalize_scene_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class ResourceRequirement(BaseModel):
    name: str
    required_quantity: int = Field(ge=1)
    available_quantity: int = Field(ge=0)
    status: Literal["ready", "missing", "maintenance"]
    note: str = ""


class ResourceCheckResponse(BaseModel):
    script_id: str
    scene_id: str | None = None
    scene_title: str
    requirements: list[ResourceRequirement] = Field(default_factory=list)
    ready_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    summary: str
    warnings: list[str] = Field(default_factory=list)


class LineReadingRequest(BaseModel):
    scene_id: str = Field(min_length=1, max_length=100)
    character: str = Field(min_length=1, max_length=100)
    mode: Literal["strict", "adaptive"] = "strict"
    role_tone: Literal["natural", "restrained", "urgent", "warm", "cold", "uncertain"] = "natural"
    context_note: str = Field(default="", max_length=1_000)
    line_index: int = Field(default=0, ge=0)
    user_text: str = Field(default="", max_length=20_000)
    session_id: str | None = Field(default=None, max_length=32)

    @field_validator("context_note")
    @classmethod
    def normalize_context_note(cls, value: str) -> str:
        return value.strip()


class LineReadingTurn(BaseModel):
    character: str
    text: str
    source_line: int = Field(ge=1)


class LineReadingTranscriptItem(BaseModel):
    """One persisted turn in a role-play session."""

    kind: Literal["partner", "actor", "feedback"]
    character: str = ""
    text: str
    source_line: int | None = Field(default=None, ge=1)


class LineReadingSession(BaseModel):
    """User-scoped state for resuming a line-reading rehearsal."""

    session_id: str
    script_id: str
    scene_id: str
    scene_title: str
    character: str
    mode: Literal["strict", "adaptive"]
    role_tone: Literal["natural", "restrained", "urgent", "warm", "cold", "uncertain"] = "natural"
    context_note: str = Field(default="", max_length=1_000)
    line_index: int = Field(default=0, ge=0)
    actor_prompt: LineReadingTurn | None = None
    transcript: list[LineReadingTranscriptItem] = Field(default_factory=list)
    turn_count: int = Field(default=0, ge=0)
    engine_counts: dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    created_at: str
    updated_at: str


class LineReadingResponse(BaseModel):
    script_id: str
    scene_id: str
    scene_title: str
    character: str
    mode: Literal["strict", "adaptive"]
    role_tone: Literal["natural", "restrained", "urgent", "warm", "cold", "uncertain"] = "natural"
    context_note: str = Field(default="", max_length=1_000)
    engine: Literal["strict", "llm", "fallback"]
    next_line_index: int | None = Field(default=None, ge=0)
    assistant_turns: list[LineReadingTurn] = Field(default_factory=list)
    actor_prompt: LineReadingTurn | None = None
    feedback: str = ""
    note: str = ""
    finished: bool = False
    session_id: str = ""
    transcript: list[LineReadingTranscriptItem] = Field(default_factory=list)
    turn_count: int = Field(default=0, ge=0)


class RehearsalFeedbackRequest(BaseModel):
    """Raw notes captured after one rehearsal session."""

    script_id: str | None = Field(default=None, max_length=100)
    scene_id: str | None = Field(default=None, max_length=100)
    rehearsal_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    participants: list[str] = Field(default_factory=list, max_length=100)
    outputs: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(min_length=1, max_length=20_000)
    analysis_mode: Literal["auto", "rules", "llm"] = "auto"

    @field_validator("script_id", "scene_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("rehearsal_date")
    @classmethod
    def validate_rehearsal_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("排练日期必须是有效的 YYYY-MM-DD") from exc
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("排练反馈不能为空")
        return value


class RehearsalFeedbackResponse(BaseModel):
    """Structured mirror of a rehearsal's raw notes."""

    record_id: str
    script_id: str | None = None
    script_title: str = ""
    scene_id: str | None = None
    scene_title: str = ""
    rehearsal_date: str
    participants: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    notes: str
    summary: str
    strengths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    engine: Literal["rules", "llm", "fallback"]
    note: str = ""
    created_at: str


class RehearsalMetricItem(BaseModel):
    """A repeated, explainable item in the rehearsal metrics summary."""

    label: str
    count: int = Field(ge=0)


class RehearsalMetricTrend(BaseModel):
    """One day's activity counts in the selected reporting window."""

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sessions: int = Field(ge=0)
    outputs: int = Field(ge=0)
    blockers: int = Field(ge=0)
    next_actions: int = Field(ge=0)


class RehearsalMetricRecentSession(BaseModel):
    """A compact pointer from a metric back to one archived feedback record."""

    record_id: str
    rehearsal_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    script_title: str = ""
    scene_title: str = ""
    outputs_count: int = Field(ge=0)
    blockers_count: int = Field(ge=0)
    next_actions_count: int = Field(ge=0)
    engine: Literal["rules", "llm", "fallback"]


class RehearsalMetricsResponse(BaseModel):
    """Deterministic, user-scoped metrics computed from archived feedback."""

    window_days: int = Field(ge=7, le=365)
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    to_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    session_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    strength_count: int = Field(ge=0)
    blocker_count: int = Field(ge=0)
    next_action_count: int = Field(ge=0)
    sessions_with_outputs: int = Field(ge=0)
    sessions_with_blockers: int = Field(ge=0)
    sessions_with_next_actions: int = Field(ge=0)
    unique_participant_count: int = Field(ge=0)
    average_participants: float = Field(ge=0)
    output_coverage: float = Field(ge=0, le=100)
    blocker_rate: float = Field(ge=0, le=100)
    next_action_rate: float = Field(ge=0, le=100)
    engine_counts: dict[str, int] = Field(default_factory=dict)
    top_strengths: list[RehearsalMetricItem] = Field(default_factory=list)
    top_blockers: list[RehearsalMetricItem] = Field(default_factory=list)
    trend: list[RehearsalMetricTrend] = Field(default_factory=list)
    recent_sessions: list[RehearsalMetricRecentSession] = Field(default_factory=list)
    note: str = ""
    generated_at: str


class RehearsalLogRequest(BaseModel):
    """A source-preserving stage-management note."""

    script_id: str | None = Field(default=None, max_length=100)
    scene_id: str | None = Field(default=None, max_length=100)
    rehearsal_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    author: str = Field(default="场记", min_length=1, max_length=100)
    category: Literal["direction", "actor", "blocking", "prop", "sound", "general"] = "general"
    content: str = Field(min_length=1, max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    source_line: int | None = Field(default=None, ge=1)

    @field_validator("script_id", "scene_id")
    @classmethod
    def normalize_log_ids(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("rehearsal_date")
    @classmethod
    def validate_log_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("场记日期必须是有效的 YYYY-MM-DD") from exc
        return value

    @field_validator("author", "content")
    @classmethod
    def normalize_log_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("场记内容不能为空")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_log_tags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            tag = value.strip()
            if tag and tag not in result:
                result.append(tag)
        return result


class RehearsalLogResponse(BaseModel):
    """Structured scene note while retaining the exact original content."""

    log_id: str
    script_id: str | None = None
    script_title: str = ""
    scene_id: str | None = None
    scene_title: str = ""
    rehearsal_date: str
    author: str
    category: Literal["direction", "actor", "blocking", "prop", "sound", "general"]
    content: str
    tags: list[str] = Field(default_factory=list)
    source_line: int | None = Field(default=None, ge=1)
    created_at: str


class SuggestionRequest(BaseModel):
    """An actor's suggestion that should remain reviewable by the troupe."""

    script_id: str | None = Field(default=None, max_length=100)
    scene_id: str | None = Field(default=None, max_length=100)
    actor_name: str = Field(default="匿名演员", min_length=1, max_length=100)
    category: Literal["performance", "blocking", "script", "team", "safety", "other"] = "other"
    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("script_id", "scene_id")
    @classmethod
    def normalize_suggestion_ids(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("actor_name", "content")
    @classmethod
    def normalize_suggestion_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("建议内容不能为空")
        return value


class SuggestionUpdateRequest(BaseModel):
    status: Literal["new", "reviewed", "accepted", "archived"]
    response: str = Field(default="", max_length=2_000)

    @field_validator("response")
    @classmethod
    def normalize_suggestion_response(cls, value: str) -> str:
        return value.strip()


class SuggestionResponse(BaseModel):
    suggestion_id: str
    script_id: str | None = None
    script_title: str = ""
    scene_id: str | None = None
    scene_title: str = ""
    actor_name: str
    category: Literal["performance", "blocking", "script", "team", "safety", "other"]
    content: str
    priority: Literal["normal", "high"] = "normal"
    status: Literal["new", "reviewed", "accepted", "archived"] = "new"
    response: str = ""
    created_at: str
    updated_at: str


class MottoRequest(BaseModel):
    """A quote or rehearsal maxim that the troupe wants to keep."""

    script_id: str | None = Field(default=None, max_length=100)
    scene_id: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=2_000)
    author: str = Field(default="奇点剧团", min_length=1, max_length=100)
    source: str = Field(default="排练现场", max_length=200)
    theme: Literal["performance", "team", "theatre", "life", "other"] = "other"
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("script_id", "scene_id")
    @classmethod
    def normalize_motto_ids(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("text", "author", "source")
    @classmethod
    def normalize_motto_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("格言内容不能为空")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_motto_tags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            tag = value.strip()
            if tag and tag not in result:
                result.append(tag)
        return result


class MottoUpdateRequest(BaseModel):
    favorite: bool


class MottoResponse(BaseModel):
    motto_id: str
    script_id: str | None = None
    script_title: str = ""
    scene_id: str | None = None
    scene_title: str = ""
    text: str
    author: str
    source: str
    theme: Literal["performance", "team", "theatre", "life", "other"]
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    created_at: str
    updated_at: str


class PromoCopyRequest(BaseModel):
    """Inputs for the publicity copy Agent; script context is optional."""

    script_id: str | None = Field(default=None, max_length=100)
    work_title: str = Field(default="奇点剧团新作", min_length=1, max_length=200)
    audience: Literal["audience", "recruitment", "media", "festival"] = "audience"
    tone: Literal["poetic", "concise", "warm", "experimental"] = "poetic"
    brief: str = Field(default="", max_length=2_000)
    analysis_mode: Literal["auto", "rules", "llm"] = "auto"

    @field_validator("script_id")
    @classmethod
    def normalize_promo_script_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("work_title")
    @classmethod
    def normalize_promo_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("作品名称不能为空")
        return value

    @field_validator("brief")
    @classmethod
    def normalize_promo_brief(cls, value: str) -> str:
        return value.strip()


class PromoCopyResponse(BaseModel):
    copy_id: str
    script_id: str | None = None
    work_title: str
    audience: Literal["audience", "recruitment", "media", "festival"]
    tone: Literal["poetic", "concise", "warm", "experimental"]
    brief: str = ""
    headline: str
    short_copy: str
    long_copy: str
    hashtags: list[str] = Field(default_factory=list)
    engine: Literal["rules", "llm", "fallback"]
    note: str = ""
    created_at: str


class ScriptRagQueryRequest(BaseModel):
    """A question grounded in one saved script version."""

    question: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=8)
    retrieval_mode: Literal["rules", "semantic"] = "rules"
    answer_mode: Literal["auto", "rules", "llm"] = "auto"

    @field_validator("question")
    @classmethod
    def normalize_rag_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("剧本问题不能为空")
        return value


class ScriptRagEvidence(BaseModel):
    """A source-backed snippet returned with every grounded answer."""

    evidence_id: str
    scene_id: str
    scene_number: int = Field(ge=1)
    scene_title: str
    source_type: Literal["scene_context", "dialogue", "stage_direction"]
    character: str = ""
    text: str
    source_line: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    match_reason: str = ""


class ScriptRagResponse(BaseModel):
    """A script answer whose evidence remains independently inspectable."""

    script_id: str
    script_title: str
    question: str
    answer: str
    evidence: list[ScriptRagEvidence] = Field(default_factory=list)
    engine: Literal["rules", "llm", "fallback"]
    retrieval_engine: Literal["rules", "semantic", "rules-fallback"]
    note: str = ""
    created_at: str


class ScriptDiffRequest(BaseModel):
    compare_script_id: str = Field(min_length=1, max_length=100)


class ScriptLineChange(BaseModel):
    change_type: Literal["added", "removed", "modified"]
    character: str
    old_text: str = ""
    new_text: str = ""
    old_source_line: int | None = Field(default=None, ge=1)
    new_source_line: int | None = Field(default=None, ge=1)


class SceneDiff(BaseModel):
    scene_key: str
    scene_number: int = Field(ge=1)
    status: Literal["added", "removed", "changed", "unchanged"]
    old_scene_id: str | None = None
    new_scene_id: str | None = None
    old_title: str = ""
    new_title: str = ""
    added_characters: list[str] = Field(default_factory=list)
    removed_characters: list[str] = Field(default_factory=list)
    added_props: list[str] = Field(default_factory=list)
    removed_props: list[str] = Field(default_factory=list)
    line_changes: list[ScriptLineChange] = Field(default_factory=list)
    impact: list[str] = Field(default_factory=list)
    summary: str = ""


class VersionDownstreamImpact(BaseModel):
    """A deterministic reminder for artifacts that may be stale after a version change."""

    impact_type: Literal["schedule", "line-reading", "resource"]
    severity: Literal["high", "medium", "info"]
    scene_key: str
    scene_number: int = Field(ge=1)
    scene_title: str = ""
    affected_characters: list[str] = Field(default_factory=list)
    affected_props: list[str] = Field(default_factory=list)
    resource_audit_matches: list[VersionResourceAuditMatch] = Field(default_factory=list)
    reason: str
    action: str


class ScriptVersionDiff(BaseModel):
    previous_script_id: str
    current_script_id: str
    previous_version_label: str
    current_version_label: str
    previous_title: str
    current_title: str
    added_scene_count: int = Field(ge=0)
    removed_scene_count: int = Field(ge=0)
    changed_scene_count: int = Field(ge=0)
    unchanged_scene_count: int = Field(ge=0)
    scenes: list[SceneDiff] = Field(default_factory=list)
    summary: str
    downstream_impacts: list[VersionDownstreamImpact] = Field(default_factory=list)
    requires_schedule_review: bool = False
    requires_line_reading_review: bool = False
    requires_resource_review: bool = False


StagePosition = Literal[
    "upstage_left",
    "upstage_center",
    "upstage_right",
    "center_left",
    "center",
    "center_right",
    "downstage_left",
    "downstage_center",
    "downstage_right",
    "unknown",
]


class StageActor(BaseModel):
    name: str
    status: Literal["onstage", "offstage", "unknown"]
    position: StagePosition = "unknown"
    source_lines: list[int] = Field(default_factory=list)


class StageProp(BaseModel):
    name: str
    position: StagePosition = "unknown"
    source_lines: list[int] = Field(default_factory=list)


class StageEvent(BaseModel):
    order: int = Field(ge=1)
    event_type: Literal["entrance", "exit", "movement", "prop", "dialogue", "other"]
    subject: str
    text: str
    source_line: int = Field(ge=1)


class StageVisualization(BaseModel):
    script_id: str
    scene_id: str
    scene_number: int = Field(ge=1)
    scene_title: str
    actors: list[StageActor] = Field(default_factory=list)
    props: list[StageProp] = Field(default_factory=list)
    events: list[StageEvent] = Field(default_factory=list)
    summary: str
    warnings: list[str] = Field(default_factory=list)


class ScheduleToolCall(BaseModel):
    """An inspectable tool invocation emitted by the scheduling Agent."""

    call_id: str
    tool_name: str
    phase: Literal["inspect", "extract", "group", "assign", "validate", "override"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "repaired", "failed"] = "completed"
    summary: str


class ScheduleAlternative(BaseModel):
    """A reviewable fallback proposal for a task that cannot be fully scheduled."""

    alternative_id: str
    kind: Literal["shorten_duration", "split_by_actor", "request_availability"]
    label: str
    reason: str
    affected_actors: list[str] = Field(default_factory=list)
    date: str | None = None
    start: str | None = None
    end: str | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    priority: Literal["low", "medium", "high"] = "medium"
    requires_human_approval: bool = True


class ScheduleManualOverride(BaseModel):
    date: str
    start: str
    end: str
    note: str = ""
    created_at: str


class ScheduleTask(BaseModel):
    task_id: str
    scene_id: str
    scene_number: int = Field(ge=1)
    title: str
    required_characters: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(ge=15, le=240)
    parallel_group: int = Field(ge=1)
    parallel_reason: str = ""
    conflict_priority: Literal["none", "low", "medium", "high"] = "none"
    alternatives: list[ScheduleAlternative] = Field(default_factory=list)
    manual_override: ScheduleManualOverride | None = None
    scheduled_date: str | None = None
    scheduled_start: str | None = None
    scheduled_end: str | None = None
    unassigned_reason: str | None = None
    status: Literal["draft", "scheduled", "unassigned", "overridden"] = "draft"


class ScheduleDraft(BaseModel):
    script_id: str
    review_status: Literal["pending", "confirmed", "edited"]
    is_preview: bool = False
    agent_run_id: str | None = None
    parent_run_id: str | None = None
    root_run_id: str | None = None
    tasks: list[ScheduleTask] = Field(default_factory=list)
    tool_calls: list[ScheduleToolCall] = Field(default_factory=list)
    created_at: str


class ScheduleBatchOverrideResponse(BaseModel):
    """Result contract for a batch confirmation; no partial write is reported."""

    script_id: str
    schedule: ScheduleDraft
    confirmed_task_ids: list[str] = Field(default_factory=list)
    overridden_count: int = Field(ge=0)
    atomic: bool = True


class ScriptAnalysis(BaseModel):
    script_id: str
    title: str
    version_label: str
    analysis_mode: Literal["deterministic", "llm", "hybrid"] = "deterministic"
    parser_version: str = "0.2.0"
    review_status: Literal["pending", "confirmed", "edited"] = "pending"
    reviewed_at: str | None = None
    review_note: str = ""
    scenes: list[Scene] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    props: list[Prop] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: list[AgentStep] = Field(default_factory=list)
    created_at: str


class ScriptSummary(BaseModel):
    script_id: str
    title: str
    version_label: str
    scene_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    prop_count: int = Field(ge=0)
    review_status: Literal["pending", "confirmed", "edited"] = "pending"
    created_at: str
