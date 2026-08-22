"""剧本解析结果的用户隔离文件存储。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.config import settings
from backend.rehearsal.models import (
    AvailabilitySlot,
    AgentRunRecord,
    BudgetLineItem,
    InvoiceRecord,
    MottoResponse,
    MusicTimelineNote,
    PromoCopyResponse,
    RehearsalFeedbackResponse,
    RehearsalLogResponse,
    ResourceInventoryItem,
    RoomBooking,
    ScheduleDraft,
    ScriptAnalysis,
    ScriptSummary,
    SuggestionResponse,
)


_SCRIPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RESOURCE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _scripts_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _script_path(user_id: str, script_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(script_id):
        raise ValueError("invalid script id")
    return _scripts_dir(user_id) / f"{script_id}.json"


def save_script(analysis: ScriptAnalysis, *, user_id: str) -> None:
    path = _script_path(user_id, analysis.script_id)
    path.write_text(
        json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_script(script_id: str, *, user_id: str) -> ScriptAnalysis | None:
    path = _script_path(user_id, script_id)
    if not path.exists():
        return None
    return ScriptAnalysis.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_scripts(*, user_id: str) -> list[ScriptSummary]:
    result: list[ScriptSummary] = []
    for path in sorted(_scripts_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            analysis = ScriptAnalysis.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        result.append(ScriptSummary(
            script_id=analysis.script_id,
            title=analysis.title,
            version_label=analysis.version_label,
            scene_count=len(analysis.scenes),
            character_count=len(analysis.characters),
            prop_count=len(analysis.props),
            review_status=analysis.review_status,
            created_at=analysis.created_at,
        ))
    return result


def _agent_runs_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "agent-runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _agent_run_path(user_id: str, run_id: str) -> Path:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid agent run id")
    return _agent_runs_dir(user_id) / f"{run_id}.json"


def save_agent_run(record: AgentRunRecord, *, user_id: str) -> None:
    _agent_run_path(user_id, record.run_id).write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_agent_run(run_id: str, *, user_id: str) -> AgentRunRecord | None:
    path = _agent_run_path(user_id, run_id)
    if not path.exists():
        return None
    try:
        return AgentRunRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def list_agent_runs(*, user_id: str, limit: int = 50) -> list[AgentRunRecord]:
    result: list[AgentRunRecord] = []
    for path in sorted(_agent_runs_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(result) >= limit:
            break
        try:
            result.append(AgentRunRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def _schedule_path(user_id: str, script_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(script_id):
        raise ValueError("invalid script id")
    path = settings.user_data_dir(user_id) / "rehearsal" / "schedules"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{script_id}.json"


def save_schedule(draft: ScheduleDraft, *, user_id: str) -> None:
    _schedule_path(user_id, draft.script_id).write_text(
        json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_schedule(script_id: str, *, user_id: str) -> ScheduleDraft | None:
    path = _schedule_path(user_id, script_id)
    if not path.exists():
        return None
    return ScheduleDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))


def delete_schedule(script_id: str, *, user_id: str) -> None:
    path = _schedule_path(user_id, script_id)
    if path.exists():
        path.unlink()


def _availability_path(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal"
    path.mkdir(parents=True, exist_ok=True)
    return path / "availability.json"


def save_availability(slots: list[AvailabilitySlot], *, user_id: str) -> None:
    _availability_path(user_id).write_text(
        json.dumps([slot.model_dump(mode="json") for slot in slots], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_availability(*, user_id: str) -> list[AvailabilitySlot]:
    path = _availability_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [AvailabilitySlot.model_validate(item) for item in payload]
    except (OSError, ValueError, TypeError):
        return []


def _feedback_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "feedback"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _feedback_path(user_id: str, record_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(record_id):
        raise ValueError("invalid feedback id")
    return _feedback_dir(user_id) / f"{record_id}.json"


def save_feedback(record: RehearsalFeedbackResponse, *, user_id: str) -> None:
    _feedback_path(user_id, record.record_id).write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_feedback(record_id: str, *, user_id: str) -> RehearsalFeedbackResponse | None:
    path = _feedback_path(user_id, record_id)
    if not path.exists():
        return None
    return RehearsalFeedbackResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_feedback(*, user_id: str) -> list[RehearsalFeedbackResponse]:
    result: list[RehearsalFeedbackResponse] = []
    for path in sorted(_feedback_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result.append(RehearsalFeedbackResponse.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def _logbook_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "logbook"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _logbook_path(user_id: str, log_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(log_id):
        raise ValueError("invalid log id")
    return _logbook_dir(user_id) / f"{log_id}.json"


def save_log(record: RehearsalLogResponse, *, user_id: str) -> None:
    _logbook_path(user_id, record.log_id).write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_logs(*, user_id: str) -> list[RehearsalLogResponse]:
    result: list[RehearsalLogResponse] = []
    for path in sorted(_logbook_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result.append(RehearsalLogResponse.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def get_log(log_id: str, *, user_id: str) -> RehearsalLogResponse | None:
    path = _logbook_path(user_id, log_id)
    if not path.exists():
        return None
    return RehearsalLogResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def delete_log(log_id: str, *, user_id: str) -> bool:
    path = _logbook_path(user_id, log_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _suggestions_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "suggestions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _suggestion_path(user_id: str, suggestion_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(suggestion_id):
        raise ValueError("invalid suggestion id")
    return _suggestions_dir(user_id) / f"{suggestion_id}.json"


def save_suggestion(suggestion: SuggestionResponse, *, user_id: str) -> None:
    _suggestion_path(user_id, suggestion.suggestion_id).write_text(
        json.dumps(suggestion.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_suggestion(suggestion_id: str, *, user_id: str) -> SuggestionResponse | None:
    path = _suggestion_path(user_id, suggestion_id)
    if not path.exists():
        return None
    return SuggestionResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_suggestions(*, user_id: str) -> list[SuggestionResponse]:
    result: list[SuggestionResponse] = []
    for path in sorted(_suggestions_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result.append(SuggestionResponse.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def delete_suggestion(suggestion_id: str, *, user_id: str) -> bool:
    path = _suggestion_path(user_id, suggestion_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _mottos_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "mottos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _motto_path(user_id: str, motto_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(motto_id):
        raise ValueError("invalid motto id")
    return _mottos_dir(user_id) / f"{motto_id}.json"


def save_motto(motto: MottoResponse, *, user_id: str) -> None:
    _motto_path(user_id, motto.motto_id).write_text(
        json.dumps(motto.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_motto(motto_id: str, *, user_id: str) -> MottoResponse | None:
    path = _motto_path(user_id, motto_id)
    if not path.exists():
        return None
    return MottoResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_mottos(*, user_id: str) -> list[MottoResponse]:
    result: list[MottoResponse] = []
    for path in sorted(_mottos_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result.append(MottoResponse.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def delete_motto(motto_id: str, *, user_id: str) -> bool:
    path = _motto_path(user_id, motto_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _promo_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "promo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _promo_path(user_id: str, copy_id: str) -> Path:
    if not _SCRIPT_ID_RE.fullmatch(copy_id):
        raise ValueError("invalid promo copy id")
    return _promo_dir(user_id) / f"{copy_id}.json"


def save_promo_copy(copy: PromoCopyResponse, *, user_id: str) -> None:
    _promo_path(user_id, copy.copy_id).write_text(
        json.dumps(copy.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_promo_copies(*, user_id: str) -> list[PromoCopyResponse]:
    result: list[PromoCopyResponse] = []
    for path in sorted(_promo_dir(user_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            result.append(PromoCopyResponse.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return result


def _resources_dir(user_id: str) -> Path:
    path = settings.user_data_dir(user_id) / "rehearsal" / "resources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inventory_path(user_id: str) -> Path:
    return _resources_dir(user_id) / "inventory.json"


def save_inventory(items: list[ResourceInventoryItem], *, user_id: str) -> None:
    _inventory_path(user_id).write_text(
        json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_inventory(*, user_id: str) -> list[ResourceInventoryItem]:
    path = _inventory_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [ResourceInventoryItem.model_validate(item) for item in payload]
    except (OSError, ValueError, TypeError):
        return []


def _rooms_path(user_id: str) -> Path:
    return _resources_dir(user_id) / "rooms.json"


def save_room_booking(booking: RoomBooking, *, user_id: str) -> None:
    bookings = list_room_bookings(user_id=user_id)
    bookings = [item for item in bookings if item.booking_id != booking.booking_id]
    bookings.append(booking)
    _rooms_path(user_id).write_text(
        json.dumps([item.model_dump(mode="json") for item in bookings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_room_bookings(*, user_id: str) -> list[RoomBooking]:
    path = _rooms_path(user_id)
    if not path.exists():
        return []
    result: list[RoomBooking] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    for item in payload:
        try:
            result.append(RoomBooking.model_validate(item))
        except (ValueError, TypeError):
            continue
    return sorted(result, key=lambda item: (item.date, item.start, item.room_name, item.booking_id))


def delete_room_booking(booking_id: str, *, user_id: str) -> bool:
    if not _RESOURCE_ID_RE.fullmatch(booking_id):
        raise ValueError("invalid booking id")
    bookings = list_room_bookings(user_id=user_id)
    remaining = [item for item in bookings if item.booking_id != booking_id]
    if len(remaining) == len(bookings):
        return False
    _rooms_path(user_id).write_text(
        json.dumps([item.model_dump(mode="json") for item in remaining], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def _music_path(user_id: str) -> Path:
    return _resources_dir(user_id) / "music.json"


def save_music_notes(notes: list[MusicTimelineNote], *, user_id: str) -> None:
    _music_path(user_id).write_text(
        json.dumps([note.model_dump(mode="json") for note in notes], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_music_notes(*, user_id: str) -> list[MusicTimelineNote]:
    path = _music_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        notes = [MusicTimelineNote.model_validate(item) for item in payload]
    except (OSError, ValueError, TypeError):
        return []
    return sorted(notes, key=lambda item: (item.start_seconds, item.track_name, item.note_id))


def _budget_path(user_id: str) -> Path:
    return _resources_dir(user_id) / "budget.json"


def save_budget_items(items: list[BudgetLineItem], *, user_id: str) -> None:
    _budget_path(user_id).write_text(
        json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_budget_items(*, user_id: str) -> list[BudgetLineItem]:
    path = _budget_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = [BudgetLineItem.model_validate(item) for item in payload]
    except (OSError, ValueError, TypeError):
        return []
    return items


def _invoices_path(user_id: str) -> Path:
    return _resources_dir(user_id) / "invoices.json"


def save_invoices(invoices: list[InvoiceRecord], *, user_id: str) -> None:
    _invoices_path(user_id).write_text(
        json.dumps([invoice.model_dump(mode="json") for invoice in invoices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_invoices(*, user_id: str) -> list[InvoiceRecord]:
    path = _invoices_path(user_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        invoices = [InvoiceRecord.model_validate(item) for item in payload]
    except (OSError, ValueError, TypeError):
        return []
    return sorted(invoices, key=lambda item: (item.invoice_date, item.invoice_id), reverse=True)
