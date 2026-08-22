"""Run the deterministic rehearsal-Agent evaluation set.

The suite deliberately exercises local rule paths, so it can run in CI and in
an interview demo without LLM or Embedding credentials. It checks observable
contracts rather than judging generated prose: structured fields, scheduling
feasibility, resource explanations, and source-backed RAG evidence.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

from evals.mock_llm import ContractMockLLM
from backend.rehearsal.agent import ScriptAnalysisAgent
from backend.rehearsal.models import (
    AvailabilitySlot,
    BudgetLineItem,
    InvoiceRecord,
    LineReadingRequest,
    MusicTimelineNote,
    ResourceInventoryItem,
    ScheduleOverrideRequest,
    ScriptRagQueryRequest,
)
from backend.rehearsal.rag_agent import ScriptRagAgent
from backend.rehearsal.resource_agent import ResourceAgent
from backend.rehearsal.schedule_agent import RehearsalScheduleAgent
from backend.rehearsal.line_reading import LineReadingAgent, LineReadingSessionAgent


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = Path(__file__).with_name("rehearsal_cases.json")


@dataclass
class CheckResult:
    name: str
    passed: bool
    actual: Any
    expected: Any


@dataclass
class CaseResult:
    case_id: str
    kind: str
    passed: bool
    checks: list[CheckResult]
    error: str = ""


def _check(
    checks: list[CheckResult],
    name: str,
    actual: Any,
    expected: Any,
    passed: bool | None = None,
) -> None:
    checks.append(CheckResult(
        name=name,
        passed=actual == expected if passed is None else passed,
        actual=actual,
        expected=expected,
    ))


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("评估集必须是非空 JSON 数组")
    return payload


def _script_text(case: dict[str, Any]) -> str:
    if "script_text" in case:
        return str(case["script_text"])
    script_path = REPO_ROOT / str(case["script_path"])
    return script_path.read_text(encoding="utf-8")


def _analysis(case: dict[str, Any]):
    return ScriptAnalysisAgent().run(
        title=str(case["title"]),
        version_label=str(case.get("version_label", "eval")),
        script_text=_script_text(case),
        script_id=f"eval-{case['id']}",
        analysis_mode=case.get("analysis_mode", "rules"),
    )


def _evaluate_script_analysis(case: dict[str, Any], checks: list[CheckResult]) -> None:
    analysis = _analysis(case)
    expected = case["expected"]
    _check(checks, "analysis_mode", analysis.analysis_mode, expected.get("analysis_mode"))
    _check(checks, "scene_numbers", [scene.number for scene in analysis.scenes], expected.get("scene_numbers"))
    _check(
        checks,
        "character_names",
        sorted(character.name for character in analysis.characters),
        sorted(expected.get("character_names", [])),
    )
    actual_props = {prop.name for prop in analysis.props}
    expected_props = set(expected.get("props_include", []))
    _check(
        checks,
        "props_include",
        sorted(actual_props & expected_props),
        sorted(expected_props),
    )
    if "costume_names" in expected:
        _check(
            checks,
            "costume_names",
            sorted(costume.name for costume in analysis.costumes),
            sorted(expected["costume_names"]),
        )
    if "costume_source_lines" in expected:
        actual_costume_lines = sorted({
            line
            for costume in analysis.costumes
            for line in costume.source_lines
        })
        _check(checks, "costume_source_lines", actual_costume_lines, sorted(expected["costume_source_lines"]))
    _check(checks, "trace_steps", [step.name for step in analysis.trace], expected.get("trace_steps"))
    source_lines_valid = all(
        scene.source.start_line >= 1
        and scene.source.end_line >= scene.source.start_line
        and all(line.source.start_line >= 1 for line in scene.lines)
        for scene in analysis.scenes
    )
    _check(checks, "all_source_lines_valid", source_lines_valid, expected.get("all_source_lines_valid", True))


def _evaluate_llm_contract(case: dict[str, Any], checks: list[CheckResult]) -> None:
    """Exercise the optional provider path with deterministic fixture output."""
    mock_config = case["mock"]
    role_tone = str(case.get("role_tone", "natural"))
    context_note = str(case.get("context_note", ""))
    mock = ContractMockLLM(
        scenes=mock_config["scenes"],
        adaptive=mock_config["adaptive"],
    )
    with ExitStack() as stack:
        stack.enter_context(patch(
            "backend.rehearsal.llm_extractor.get_llm",
            return_value=mock,
        ))
        stack.enter_context(patch(
            "backend.rehearsal.line_reading.get_llm",
            return_value=mock,
        ))
        analysis = _analysis(case)
        line_response = LineReadingAgent().respond(
            analysis,
            LineReadingRequest(
                scene_id=str(case["scene_id"]),
                character=str(case["character"]),
                mode="adaptive",
                role_tone=role_tone,
                context_note=context_note,
                line_index=int(case.get("line_index", 0)),
                user_text=str(case.get("user_text", "")),
            ),
        )
        session_agent = LineReadingSessionAgent()
        session_start, session = session_agent.advance(
            analysis,
            LineReadingRequest(
                scene_id=str(case["scene_id"]),
                character=str(case["character"]),
                mode="adaptive",
                role_tone=role_tone,
                context_note=context_note,
                line_index=int(case.get("line_index", 0)),
            ),
        )
        session_resume, resumed_session = session_agent.advance(
            analysis,
            LineReadingRequest(
                scene_id=str(case["scene_id"]),
                character=str(case["character"]),
                mode="adaptive",
                role_tone=role_tone,
                context_note=context_note,
                line_index=99,
                user_text=str(case["expected"]["session"]["user_text"]),
                session_id=session.session_id,
            ),
            session=session,
        )

    expected = case["expected"]
    _check(checks, "analysis_mode", analysis.analysis_mode, expected["analysis_mode"])
    _check(checks, "scene_numbers", [scene.number for scene in analysis.scenes], expected["scene_numbers"])
    _check(
        checks,
        "character_names",
        sorted(character.name for character in analysis.characters),
        sorted(expected["character_names"]),
    )
    _check(
        checks,
        "props_include",
        sorted({prop.name for prop in analysis.props} & set(expected["props_include"])),
        sorted(expected["props_include"]),
    )
    _check(checks, "mock_call_count", len(mock.calls), expected["mock_call_count"])
    adaptive_prompts = [
        messages[-1].get("content", "")
        for messages in mock.calls
        if messages and "请改写以下非练习者参考台词" in messages[-1].get("content", "")
    ]
    profile_contract_ok = bool(adaptive_prompts) and all(
        f"（{role_tone}）" in prompt and context_note in prompt
        for prompt in adaptive_prompts
    )
    _check(checks, "adaptive_profile_contract", profile_contract_ok, True, passed=profile_contract_ok)
    memory_text = expected["session"].get("context_memory_contains", "")
    memory_contract_ok = bool(memory_text) and len(adaptive_prompts) >= 2 and memory_text in adaptive_prompts[-1]
    _check(checks, "adaptive_context_memory", memory_contract_ok, True, passed=memory_contract_ok)
    source_lines_valid = all(
        line.source.start_line >= 1
        and line.source.end_line >= line.source.start_line
        for scene in analysis.scenes
        for line in scene.lines
    )
    _check(checks, "all_source_lines_valid", source_lines_valid, True)

    anchored = expected["anchored_line"]
    anchored_scene = next(scene for scene in analysis.scenes if scene.number == anchored["scene_number"])
    anchored_line = next(
        line for line in anchored_scene.lines if line.character == anchored["character"]
    )
    _check(checks, "source_anchor_text", anchored_line.text, anchored["text"])
    warning_found = any(expected["warning_contains"] in warning for warning in analysis.warnings)
    _check(checks, "source_anchor_warning", warning_found, True, passed=warning_found)

    _check(checks, "adaptive_engine", line_response.engine, expected["adaptive_engine"])
    _check(checks, "adaptive_role_tone", line_response.role_tone, role_tone)
    _check(checks, "adaptive_context_note", line_response.context_note, context_note)
    _check(
        checks,
        "adaptive_characters",
        [turn.character for turn in line_response.assistant_turns],
        expected["adaptive_characters"],
    )
    _check(
        checks,
        "adaptive_source_lines",
        [turn.source_line for turn in line_response.assistant_turns],
        expected["adaptive_source_lines"],
    )
    _check(
        checks,
        "adaptive_texts",
        [turn.text for turn in line_response.assistant_turns],
        expected["adaptive_texts"],
    )
    session_expected = expected["session"]
    _check(checks, "session_cursor", resumed_session.line_index, session_expected["cursor"])
    _check(checks, "session_turn_count", resumed_session.turn_count, session_expected["turn_count"])
    _check(
        checks,
        "session_transcript_kinds",
        [item.kind for item in resumed_session.transcript],
        session_expected["transcript_kinds"],
    )
    _check(checks, "session_engine_counts", resumed_session.engine_counts, session_expected["engine_counts"])
    _check(checks, "session_role_tone", resumed_session.role_tone, role_tone)
    _check(checks, "session_context_note", resumed_session.context_note, context_note)
    _check(
        checks,
        "session_id_stable",
        session_start.session_id == session_resume.session_id == resumed_session.session_id,
        True,
    )
    _check(
        checks,
        "session_partner_source_lines",
        [turn.source_line for turn in session_resume.assistant_turns],
        session_expected["partner_source_lines"],
    )


def _evaluate_schedule(case: dict[str, Any], checks: list[CheckResult]) -> None:
    analysis = _analysis(case).model_copy(update={"review_status": case.get("review_status", "confirmed")})
    agent = RehearsalScheduleAgent()
    expected = case["expected"]
    linkage = expected.get("run_linkage", {})
    draft_run_id = linkage.get("draft_run_id")
    plan_run_id = linkage.get("plan_run_id")
    music_notes = [MusicTimelineNote(**payload) for payload in case.get("music_notes", [])]
    budget_items = [BudgetLineItem(**payload) for payload in case.get("budget_items", [])]
    invoices = [InvoiceRecord(**payload) for payload in case.get("invoices", [])]
    inventory = [ResourceInventoryItem(**payload) for payload in case.get("inventory", [])]
    draft = agent.run(
        analysis,
        default_minutes=int(case.get("default_minutes", 45)),
        agent_run_id=draft_run_id,
        root_run_id=draft_run_id,
        music_notes=music_notes,
        budget_items=budget_items,
        invoices=invoices,
        inventory=inventory,
    )
    slots = [AvailabilitySlot(**payload) for payload in case.get("slots", [])]
    planned = agent.assign(
        draft,
        slots,
        agent_run_id=plan_run_id,
        parent_run_id=draft_run_id,
        root_run_id=draft_run_id,
    )
    statuses = [task.status for task in planned.tasks]
    _check(checks, "task_count", len(planned.tasks), expected.get("task_count"))
    _check(checks, "scheduled_count", statuses.count("scheduled"), expected.get("scheduled_count"))
    _check(checks, "unassigned_count", statuses.count("unassigned"), expected.get("unassigned_count"))
    if "tool_names" in expected:
        _check(checks, "tool_names", [call.tool_name for call in planned.tool_calls], expected["tool_names"])
    if "tool_phases" in expected:
        _check(checks, "tool_phases", [call.phase for call in planned.tool_calls], expected["tool_phases"])
    if "tool_result_keys_by_name" in expected:
        for tool_name, required_keys in expected["tool_result_keys_by_name"].items():
            calls = [call for call in planned.tool_calls if call.tool_name == tool_name]
            contract_ok = bool(calls) and all(
                set(required_keys).issubset(call.result)
                for call in calls
            )
            _check(checks, f"tool_result_contract:{tool_name}", contract_ok, True, passed=contract_ok)
    resource_expected = expected.get("resource_context")
    if resource_expected:
        resource_context = planned.resource_context
        _check(checks, "resource_context_present", resource_context is not None, True)
        if resource_context is not None:
            _check(checks, "resource_music_count", len(resource_context.music_cues), resource_expected["music_count"])
            _check(checks, "resource_budget_count", len(resource_context.budget_items), resource_expected["budget_count"])
            _check(checks, "resource_invoice_count", len(resource_context.invoices), resource_expected["invoice_count"])
            _check(checks, "resource_costume_count", len(resource_context.costume_inventory), resource_expected["costume_count"])
            if "costume_requirement_count" in resource_expected:
                _check(
                    checks,
                    "resource_costume_requirement_count",
                    len(resource_context.costume_requirements),
                    resource_expected["costume_requirement_count"],
                )
            if "unmatched_costume_requirement_count" in resource_expected:
                _check(
                    checks,
                    "resource_unmatched_costume_requirement_count",
                    resource_context.unmatched_costume_requirement_count,
                    resource_expected["unmatched_costume_requirement_count"],
                )
            _check(checks, "resource_estimated_total", resource_context.estimated_total, resource_expected["estimated_total"])
            _check(checks, "resource_actual_total", resource_context.actual_total, resource_expected["actual_total"])
            _check(checks, "resource_invoice_total", resource_context.invoice_total, resource_expected["invoice_total"])
            _check(checks, "resource_verified_invoice_total", resource_context.verified_invoice_total, resource_expected["verified_invoice_total"])
            _check(checks, "resource_unlinked_invoice_count", resource_context.unlinked_invoice_count, resource_expected["unlinked_invoice_count"])
            _check(checks, "resource_costume_issue_count", resource_context.costume_issue_count, resource_expected["costume_issue_count"])
            warning_contains = resource_expected.get("warning_contains")
            if warning_contains:
                warning_found = any(warning_contains in warning for warning in resource_context.warnings)
                _check(checks, "resource_warning", warning_found, True, passed=warning_found)
            if "warning_count" in resource_expected:
                _check(checks, "resource_warning_count", len(resource_context.warnings), resource_expected["warning_count"])
            costume_warning_contains = resource_expected.get("costume_warning_contains")
            if costume_warning_contains:
                costume_warning_found = any(costume_warning_contains in warning for warning in resource_context.warnings)
                _check(checks, "resource_costume_warning", costume_warning_found, True, passed=costume_warning_found)
        resource_calls = [call for call in planned.tool_calls if call.tool_name == "inspect_rehearsal_resources"]
        _check(checks, "resource_tool_call", len(resource_calls) == 1, True)
    if "parallel_groups" in expected:
        _check(checks, "parallel_groups", [task.parallel_group for task in draft.tasks], expected["parallel_groups"])
    if "first_task_end_equals_second_start" in expected and len(planned.tasks) >= 2:
        _check(
            checks,
            "first_task_end_equals_second_start",
            planned.tasks[0].scheduled_end == planned.tasks[1].scheduled_start,
            expected["first_task_end_equals_second_start"],
        )
    if expected.get("second_task_reason_contains"):
        reason = draft.tasks[1].parallel_reason if len(draft.tasks) > 1 else ""
        found = expected["second_task_reason_contains"] in reason
        _check(checks, "second_task_reason_contains", found, True, passed=found)
    if expected.get("unassigned_reason_contains"):
        reasons = [task.unassigned_reason or "" for task in planned.tasks if task.status == "unassigned"]
        found = any(expected["unassigned_reason_contains"] in reason for reason in reasons)
        _check(checks, "unassigned_reason_contains", found, True, passed=found)
    if expected.get("conflict_priority"):
        priorities = sorted({task.conflict_priority for task in planned.tasks if task.status == "unassigned"})
        _check(checks, "conflict_priority", priorities, [expected["conflict_priority"]])
    if expected.get("alternative_kinds"):
        kinds = sorted({alternative.kind for task in planned.tasks for alternative in task.alternatives})
        _check(checks, "alternative_kinds", kinds, sorted(expected["alternative_kinds"]))
    if linkage:
        _check(checks, "draft_run_id", draft.agent_run_id, draft_run_id)
        _check(checks, "plan_run_id", planned.agent_run_id, plan_run_id)
        _check(checks, "parent_run_id", planned.parent_run_id, draft_run_id)
        _check(checks, "root_run_id", planned.root_run_id, draft_run_id)
    batch_expected = expected.get("batch_override")
    if batch_expected:
        item_specs = batch_expected.get("items") or [batch_expected] * len(planned.tasks)
        if len(item_specs) != len(planned.tasks):
            raise ValueError("batch override eval must provide one slot per task")
        overrides = [ScheduleOverrideRequest(
            task_id=task.task_id,
            date=slot["date"],
            start=slot["start"],
            end=slot["end"],
            room_name=slot.get("room_name"),
            note="eval batch confirmation",
        ) for task, slot in zip(planned.tasks, item_specs)]
        confirmed = agent.apply_manual_overrides(planned, overrides, agent_run_id="3" * 32)
        _check(
            checks,
            "batch_override_statuses",
            [task.status for task in confirmed.tasks],
            ["overridden"] * len(planned.tasks),
        )
        batch_call = confirmed.tool_calls[-1]
        _check(checks, "batch_override_tool_name", batch_call.tool_name, "apply_manual_override_batch")
        _check(checks, "batch_override_atomic", batch_call.result.get("atomic"), True)
        _check(checks, "batch_override_count", batch_call.result.get("overridden_count"), batch_expected["count"])
        if batch_expected.get("room_tool"):
            room_calls = [call for call in confirmed.tool_calls if call.tool_name == "validate_room_booking"]
            room_ok = bool(room_calls) and room_calls[-1].result == {
                "status": "available",
                "checked_count": sum(1 for item in overrides if item.room_name),
                "conflict_count": 0,
            }
            _check(checks, "batch_override_room_tool", room_ok, True, passed=room_ok)
        repeat_message = batch_expected.get("repeat_error_contains")
        if repeat_message:
            try:
                agent.apply_manual_overrides(confirmed, overrides)
            except ValueError as exc:
                found = repeat_message in str(exc)
                _check(checks, "batch_override_repeat_rejected", found, True, passed=found)
            else:
                _check(checks, "batch_override_repeat_rejected", False, True, passed=False)
    for error_index, error_case in enumerate(expected.get("batch_override_errors", []), start=1):
        item_specs = error_case["items"]
        task_indices = error_case.get("task_indices", list(range(len(item_specs))))
        if len(item_specs) != len(task_indices):
            raise ValueError("batch override error eval must pair each slot with a task index")
        if any(index < 0 or index >= len(planned.tasks) for index in task_indices):
            raise ValueError("batch override error eval task index is out of range")
        overrides = [ScheduleOverrideRequest(
            task_id=planned.tasks[task_index].task_id,
            date=slot["date"],
            start=slot["start"],
            end=slot["end"],
            note="eval batch boundary",
        ) for task_index, slot in zip(task_indices, item_specs)]
        try:
            agent.apply_manual_overrides(planned, overrides)
        except ValueError as exc:
            message = str(exc)
            expected_message = error_case["message_contains"]
            found = expected_message in message
            _check(checks, f"batch_override_error_{error_index}", found, True, passed=found)
        else:
            _check(checks, f"batch_override_error_{error_index}", False, True, passed=False)


def _evaluate_resource_check(case: dict[str, Any], checks: list[CheckResult]) -> None:
    analysis = _analysis(case)
    scene_number = int(case["scene_number"])
    scene = next(scene for scene in analysis.scenes if scene.number == scene_number)
    inventory = [ResourceInventoryItem(**payload) for payload in case.get("inventory", [])]
    response = ResourceAgent().check(analysis, inventory, scene_id=scene.scene_id)
    expected = case["expected"]
    actual_statuses = {item.name: item.status for item in response.requirements}
    for name, status in expected.get("status_by_name", {}).items():
        _check(checks, f"status:{name}", actual_statuses.get(name), status)
    if "ready_count" in expected:
        _check(checks, "ready_count", response.ready_count, expected["ready_count"])
    actual_notes = {item.name: item.note for item in response.requirements}
    for name, text in expected.get("requirement_note_by_name", {}).items():
        found = text in actual_notes.get(name, "")
        _check(checks, f"note:{name}", found, True, passed=found)
    if expected.get("has_warning_containing"):
        found = any(expected["has_warning_containing"] in warning for warning in response.warnings)
        _check(checks, "warning_contains", found, True, passed=found)


def _evaluate_rag(case: dict[str, Any], checks: list[CheckResult]) -> None:
    analysis = _analysis(case)
    request = ScriptRagQueryRequest(
        question=str(case["question"]),
        answer_mode=case.get("answer_mode", "rules"),
        retrieval_mode=case.get("retrieval_mode", "rules"),
    )
    response = ScriptRagAgent().answer(analysis, request, user_id=f"eval-user-{case['id']}")
    expected = case["expected"]
    _check(checks, "engine", response.engine, expected.get("engine"))
    _check(checks, "retrieval_engine", response.retrieval_engine, expected.get("retrieval_engine"))
    if "evidence_count" in expected:
        _check(checks, "evidence_count", len(response.evidence), expected["evidence_count"])
    if "evidence_count_min" in expected:
        _check(
            checks,
            "evidence_count_min",
            len(response.evidence),
            expected["evidence_count_min"],
            passed=len(response.evidence) >= expected["evidence_count_min"],
        )
    for text in expected.get("evidence_text_contains", []):
        found = any(text in item.text for item in response.evidence)
        _check(checks, f"evidence_contains:{text}", found, True, passed=found)
    if expected.get("all_source_lines_valid"):
        source_lines_valid = all(item.source_line >= 1 for item in response.evidence)
        _check(checks, "all_source_lines_valid", source_lines_valid, True, passed=source_lines_valid)
    if expected.get("answer_contains_evidence_id"):
        found = bool(response.evidence) and all(item.evidence_id in response.answer for item in response.evidence)
        _check(checks, "answer_contains_evidence_id", found, True, passed=found)
    if expected.get("answer_contains"):
        found = expected["answer_contains"] in response.answer
        _check(checks, "answer_contains", found, True, passed=found)


def _evaluate_line_reading_session(case: dict[str, Any], checks: list[CheckResult]) -> None:
    analysis = _analysis(case)
    agent = LineReadingSessionAgent()
    first, session = agent.advance(
        analysis,
        LineReadingRequest(
            scene_id=str(case["scene_id"]),
            character=str(case["character"]),
            mode=case.get("mode", "strict"),
        ),
    )
    second, finished_session = agent.advance(
        analysis,
        LineReadingRequest(
            scene_id=str(case["scene_id"]),
            character=str(case["character"]),
            mode=case.get("mode", "strict"),
            line_index=99,
            user_text="我来了。",
            session_id=session.session_id,
        ),
        session=session,
    )
    expected = case["expected"]
    _check(checks, "first_engine", first.engine, expected.get("first_engine"))
    _check(checks, "first_turn_count", first.turn_count, expected.get("first_turn_count"))
    _check(checks, "second_finished", second.finished, expected.get("second_finished"))
    _check(checks, "second_line_index", finished_session.line_index, expected.get("second_line_index"))
    _check(checks, "transcript_kinds", [item.kind for item in finished_session.transcript], expected.get("transcript_kinds"))
    _check(checks, "session_id_stable", first.session_id == second.session_id == session.session_id, expected.get("session_id_stable"))
    source_lines_valid = all(
        item.source_line is None or item.source_line >= 1
        for item in finished_session.transcript
    )
    _check(checks, "source_lines_valid", source_lines_valid, expected.get("source_lines_valid", True))


def _run_case(case: dict[str, Any]) -> CaseResult:
    checks: list[CheckResult] = []
    try:
        kind = case["kind"]
        if kind == "script_analysis":
            _evaluate_script_analysis(case, checks)
        elif kind == "llm_contract":
            _evaluate_llm_contract(case, checks)
        elif kind == "schedule":
            _evaluate_schedule(case, checks)
        elif kind == "resource_check":
            _evaluate_resource_check(case, checks)
        elif kind == "rag":
            _evaluate_rag(case, checks)
        elif kind == "line_reading_session":
            _evaluate_line_reading_session(case, checks)
        else:
            raise ValueError(f"未知评估类型：{kind}")
    except Exception as exc:  # noqa: BLE001 - a failed case should be visible in the report
        return CaseResult(
            case_id=str(case.get("id", "unknown")),
            kind=str(case.get("kind", "unknown")),
            passed=False,
            checks=checks,
            error=f"{exc.__class__.__name__}: {exc}",
        )
    return CaseResult(
        case_id=str(case["id"]),
        kind=str(case["kind"]),
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def evaluate_cases(cases_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(cases_path) if cases_path else DEFAULT_CASES_PATH
    cases = _load_cases(path)
    results = [_run_case(case) for case in cases]
    passed = sum(result.passed for result in results)
    total = len(results)
    return {
        "suite": "qidian-rehearsal-agent",
        "cases_path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "cases": [asdict(result) for result in results],
    }


def run_evaluation(cases_path: str | Path | None = None) -> dict[str, Any]:
    """Compatibility name for tests and future CI callers."""
    return evaluate_cases(cases_path)


def main() -> int:
    report = evaluate_cases()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
