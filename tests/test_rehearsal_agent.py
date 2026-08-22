from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from backend.config import settings
from backend.llm_provider import ChatLLM
from backend.rehearsal.agent import ScriptAnalysisAgent
from backend.rehearsal.feedback_agent import RehearsalMirrorAgent
from backend.rehearsal.finance_agent import ResourceFinanceAgent
from backend.rehearsal.line_reading import LineReadingAgent, LineReadingSessionAgent
from backend.rehearsal.logbook_agent import RehearsalLogAgent
from backend.rehearsal.metrics_agent import RehearsalMetricsAgent
from backend.rehearsal.motto_agent import MottoAgent
from backend.rehearsal.promo_agent import PromoCopyAgent
from backend.rehearsal.rag_agent import ScriptRagAgent
from backend.rehearsal.resource_agent import ResourceAgent, ResourceAuditAgent, room_booking_conflicts
from backend.rehearsal.run_log import outcome_status, record_agent_run
from backend.rehearsal.run_metrics import AgentRunMetricsAgent
from backend.rehearsal.storage import get_agent_run, list_agent_runs, list_resource_audits, save_resource_audit
from backend.rehearsal.suggestion_agent import SuggestionInboxAgent
from backend.rehearsal.models import (
    AvailabilitySlot,
    AgentRunRecord,
    AgentStep,
    BudgetLineItem,
    InvoiceRecord,
    LineReadingRequest,
    MottoRequest,
    MottoUpdateRequest,
    PromoCopyRequest,
    ScriptRagQueryRequest,
    RehearsalFeedbackRequest,
    RehearsalLogRequest,
    ResourceInventoryItem,
    ResourceAuditRecord,
    MusicTimelineNote,
    RoomBooking,
    RoomBookingRequest,
    Scene,
    ScheduleOverrideRequest,
    ScriptAnalysis,
    SourceSpan,
    SuggestionRequest,
    SuggestionUpdateRequest,
)
from backend.rehearsal.schedule_agent import RehearsalScheduleAgent
from backend.rehearsal.stage_agent import StageVisualizationAgent
from backend.rehearsal.version_diff import ScriptVersionDiffAgent, attach_resource_audit_matches


def test_script_agent_extracts_scenes_characters_lines_and_props():
    script = Path("docs/examples/qidian-demo-script.md").read_text(encoding="utf-8")

    result = ScriptAnalysisAgent().run(
        title="轨道之外",
        version_label="v1",
        script_text=script,
    )

    assert [scene.number for scene in result.scenes] == [1, 2]
    assert {character.name for character in result.characters} == {"导演", "小林", "许教授", "小周"}
    assert result.scenes[0].lines[0].text.startswith("所有人先不要急着走位")
    assert {prop.name for prop in result.props} >= {"椅子", "手电筒", "信封", "纸条", "手机"}
    assert [step.name for step in result.trace] == [
        "ingest",
        "split_scenes",
        "extract_entities_parallel",
        "validate",
        "repair",
    ]


def test_llm_scene_extraction_anchors_model_text_to_source():
    fake_llm = SimpleNamespace(
        last_attempts=1,
        invoke=lambda _messages: (
            '{"title":"短场","characters":["小林"],"props":["椅子"],'
            '"lines":[{"character":"小林","text":"请把椅子放这里。",'
            '"start_line":2,"end_line":2}]}'
        ),
    )

    with patch("backend.rehearsal.llm_extractor.get_llm", return_value=fake_llm):
        result = ScriptAnalysisAgent().run(
            title="短场",
            version_label="mock",
            script_text="第一场\n小林：请把椅子放到这里。",
            analysis_mode="llm",
            user_id="mock-user",
        )

    assert result.analysis_mode == "llm"
    assert result.scenes[0].lines[0].text == "请把椅子放到这里。"
    assert any("内容与原文不一致" in warning for warning in result.warnings)


def test_script_agent_keeps_source_line_for_human_review():
    result = ScriptAnalysisAgent().run(
        title="短场",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。",
    )

    line = result.scenes[0].lines[0]
    assert line.source.start_line == 2
    assert line.source.excerpt == "小林：请把椅子放到这里。"


def test_script_agent_repairs_missing_scene_header_conservatively():
    result = ScriptAnalysisAgent().run(
        title="无分场剧本",
        version_label="draft",
        script_text="导演：先读一遍。\n小林：好。",
    )

    assert len(result.scenes) == 1
    assert result.scenes[0].number == 1
    assert any("未识别到分场标题" in warning for warning in result.warnings)


def test_schedule_agent_keeps_formal_draft_gated_by_human_review():
    analysis = ScriptAnalysisAgent().run(
        title="待确认剧本",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。",
    )

    try:
        RehearsalScheduleAgent().run(analysis)
    except ValueError as exc:
        assert "人工确认" in str(exc)
    else:
        raise AssertionError("pending analysis should not create a formal draft")


def test_schedule_agent_can_create_and_assign_an_unconfirmed_preview():
    analysis = ScriptAnalysisAgent().run(
        title="预览剧本",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。\n导演：我们先确认节奏。",
    )
    agent = RehearsalScheduleAgent()

    preview = agent.run(analysis, preview=True)
    assert preview.is_preview is True
    assert preview.review_status == "pending"

    planned = agent.assign(preview, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00"),
        AvailabilitySlot(actor="导演", date="2026-08-25", start="19:00", end="21:00"),
    ])
    assert planned.is_preview is True
    assert planned.tasks[0].status == "scheduled"


def test_schedule_agent_explains_missing_common_time():
    analysis = ScriptAnalysisAgent().run(
        title="冲突剧本",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n导演：好。",
    )
    analysis.review_status = "confirmed"
    draft = RehearsalScheduleAgent().run(analysis)
    planned = RehearsalScheduleAgent().assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="20:00"),
        AvailabilitySlot(actor="导演", date="2026-08-25", start="20:00", end="21:00"),
    ])

    assert planned.tasks[0].status == "unassigned"
    assert planned.tasks[0].unassigned_reason == "演员之间没有共同的空闲时间段"
    assert planned.tasks[0].conflict_priority == "high"
    assert planned.tasks[0].alternatives[0].kind == "split_by_actor"
    assert planned.tool_calls[-2].result["alternatives"]


def test_schedule_agent_proposes_shorter_slot_when_full_duration_does_not_fit():
    analysis = ScriptAnalysisAgent().run(
        title="短时替代方案",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n导演：好。",
    )
    analysis.review_status = "confirmed"
    draft = RehearsalScheduleAgent().run(analysis, default_minutes=45)
    planned = RehearsalScheduleAgent().assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="19:45"),
        AvailabilitySlot(actor="导演", date="2026-08-25", start="19:30", end="20:30"),
    ])

    task = planned.tasks[0]
    assert task.status == "unassigned"
    assert task.conflict_priority == "medium"
    shorter = next(item for item in task.alternatives if item.kind == "shorten_duration")
    assert (shorter.date, shorter.start, shorter.end, shorter.duration_minutes) == (
        "2026-08-25", "19:30", "19:45", 15,
    )


def test_schedule_agent_keeps_manual_override_distinct_from_availability_match():
    analysis = ScriptAnalysisAgent().run(
        title="人工覆盖",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n导演：好。",
    )
    analysis.review_status = "confirmed"
    agent = RehearsalScheduleAgent()
    draft = agent.run(analysis)
    planned = agent.assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="20:00"),
    ])
    overridden = agent.apply_manual_override(
        planned,
        task_id=planned.tasks[0].task_id,
        date="2026-08-26",
        start="19:00",
        end="20:00",
        note="导演确认临时到场",
        agent_run_id="3" * 32,
        parent_run_id=planned.agent_run_id,
        root_run_id=planned.root_run_id,
    )

    task = overridden.tasks[0]
    assert task.status == "overridden"
    assert task.manual_override is not None
    assert task.manual_override.note == "导演确认临时到场"
    assert overridden.tool_calls[-1].tool_name == "apply_manual_override"


def test_schedule_agent_checks_room_booking_before_manual_confirmation():
    analysis = ScriptAnalysisAgent().run(
        title="排练室约束",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n导演：好。",
    ).model_copy(update={"review_status": "confirmed"})
    agent = RehearsalScheduleAgent()
    draft = agent.run(analysis)
    booking = RoomBooking(
        booking_id="room-booking",
        room_name="排练室 A",
        date="2026-08-26",
        start="19:00",
        end="20:00",
        purpose="其他剧组排练",
    )

    try:
        agent.apply_manual_override(
            draft,
            task_id=draft.tasks[0].task_id,
            date="2026-08-26",
            start="19:00",
            end="20:00",
            room_name="排练室 A",
            room_bookings=[booking],
        )
    except ValueError as exc:
        assert "已有预约" in str(exc)
    else:
        raise AssertionError("a booked rehearsal room must reject manual confirmation")

    available = agent.apply_manual_override(
        draft,
        task_id=draft.tasks[0].task_id,
        date="2026-08-26",
        start="19:00",
        end="20:00",
        room_name="排练室 B",
        room_bookings=[booking],
    )
    assert available.tasks[0].manual_override is not None
    assert available.tasks[0].manual_override.room_name == "排练室 B"
    assert [call.tool_name for call in available.tool_calls[-2:]] == [
        "validate_room_booking",
        "apply_manual_override",
    ]


def test_schedule_agent_batch_override_is_atomic_and_exposes_contract():
    analysis = ScriptAnalysisAgent().run(
        title="批量确认",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n第二场\n小周：继续。",
        script_id="batch-override",
        analysis_mode="rules",
    ).model_copy(update={"review_status": "confirmed"})
    agent = RehearsalScheduleAgent()
    draft = agent.run(analysis, default_minutes=45)
    planned = agent.assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00"),
        AvailabilitySlot(actor="小周", date="2026-08-25", start="19:00", end="21:00"),
    ])
    overrides = [
        ScheduleOverrideRequest(
            task_id=task.task_id,
            date="2026-08-26",
            start="19:00",
            end="20:00",
            note="导演批量确认",
        )
        for task in planned.tasks
    ]

    confirmed = agent.apply_manual_overrides(planned, overrides, agent_run_id="4" * 32)
    assert [task.status for task in confirmed.tasks] == ["overridden", "overridden"]
    assert confirmed.tool_calls[-1].tool_name == "apply_manual_override_batch"
    assert confirmed.tool_calls[-1].result == {
        "status": "overridden",
        "confirmed_task_ids": [task.task_id for task in planned.tasks],
        "overridden_count": 2,
        "atomic": True,
    }

    room_conflict_overrides = [item.model_copy(update={
        "date": "2026-08-27",
        "start": "19:00",
        "end": "20:00",
        "room_name": "排练室 A",
    }) for item in overrides]
    try:
        agent.apply_manual_overrides(planned, room_conflict_overrides)
    except ValueError as exc:
        assert "批量确认存在排练室冲突" in str(exc)
    else:
        raise AssertionError("overlapping rooms must reject an atomic batch")
    assert [task.status for task in planned.tasks] == ["scheduled", "scheduled"]

    try:
        agent.apply_manual_overrides(confirmed, overrides)
    except ValueError as exc:
        assert "批量重复提交被拒绝" in str(exc)
    else:
        raise AssertionError("already overridden tasks must reject a repeated batch")
    assert len(confirmed.tool_calls) == len(planned.tool_calls) + 1

    invalid_overrides = [
        overrides[0],
        ScheduleOverrideRequest(
            task_id=overrides[1].task_id,
            date="2026-08-26",
            start="19:00",
            end="19:20",
        ),
    ]
    try:
        agent.apply_manual_overrides(planned, invalid_overrides)
    except ValueError as exc:
        assert "不能少于预计时长" in str(exc)
    else:
        raise AssertionError("an invalid item must reject the complete batch")
    assert [task.status for task in planned.tasks] == ["scheduled", "scheduled"]


def test_schedule_agent_batch_override_rejects_resource_conflicts_and_duplicates():
    analysis = ScriptAnalysis(
        script_id="batch-boundaries",
        title="批量边界",
        version_label="v1",
        review_status="confirmed",
        scenes=[
            Scene(
                scene_id="scene-1",
                number=1,
                title="第一场",
                characters=["小林"],
                props=["椅子"],
                source=SourceSpan(start_line=1, end_line=2),
            ),
            Scene(
                scene_id="scene-2",
                number=2,
                title="第二场",
                characters=["小周"],
                props=["椅子"],
                source=SourceSpan(start_line=3, end_line=4),
            ),
        ],
        created_at="2026-08-25T00:00:00Z",
    )
    agent = RehearsalScheduleAgent()
    draft = agent.run(analysis, default_minutes=45)
    planned = agent.assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00"),
        AvailabilitySlot(actor="小周", date="2026-08-25", start="19:00", end="21:00"),
    ])
    same_slot = [ScheduleOverrideRequest(
        task_id=task.task_id,
        date="2026-08-26",
        start="19:00",
        end="19:45",
    ) for task in planned.tasks]

    try:
        agent.apply_manual_overrides(planned, same_slot)
    except ValueError as exc:
        assert "批量确认存在资源冲突" in str(exc)
    else:
        raise AssertionError("shared props must reject overlapping batch overrides")
    assert [task.status for task in planned.tasks] == ["scheduled", "scheduled"]

    try:
        agent.apply_manual_overrides(planned, [same_slot[0], same_slot[0]])
    except ValueError as exc:
        assert "不能重复包含同一排练任务" in str(exc)
    else:
        raise AssertionError("duplicate task ids must reject the complete batch")
    assert [task.status for task in planned.tasks] == ["scheduled", "scheduled"]


def test_availability_slot_rejects_invalid_calendar_and_interval():
    invalid_values = [
        {"actor": "小林", "date": "2026-02-30", "start": "19:00", "end": "21:00"},
        {"actor": "小林", "date": "2026-08-25", "start": "21:00", "end": "21:00"},
        {"actor": "小林", "date": "2026-08-25", "start": "25:00", "end": "26:00"},
    ]
    for values in invalid_values:
        try:
            AvailabilitySlot(**values)
        except ValidationError:
            continue
        raise AssertionError(f"invalid availability should be rejected: {values}")


def test_schedule_agent_explains_missing_actor_time():
    analysis = ScriptAnalysisAgent().run(
        title="缺档期剧本",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n导演：好。",
    )
    analysis.review_status = "confirmed"
    draft = RehearsalScheduleAgent().run(analysis)
    planned = RehearsalScheduleAgent().assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00"),
    ])

    assert planned.tasks[0].status == "unassigned"
    assert planned.tasks[0].unassigned_reason == "缺少演员可用时间：导演"


def test_schedule_agent_keeps_same_actor_tasks_non_overlapping():
    analysis = ScriptAnalysis(
        script_id="same-actor",
        title="连续排练",
        version_label="v1",
        review_status="confirmed",
        scenes=[
            Scene(
                scene_id="scene-1",
                number=1,
                title="第一场",
                characters=["小林"],
                source=SourceSpan(start_line=1, end_line=2),
            ),
            Scene(
                scene_id="scene-2",
                number=2,
                title="第二场",
                characters=["小林"],
                source=SourceSpan(start_line=3, end_line=4),
            ),
        ],
        created_at="2026-08-25T00:00:00Z",
    )
    draft = RehearsalScheduleAgent().run(analysis, default_minutes=60)
    planned = RehearsalScheduleAgent().assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="22:00"),
    ])

    assert [task.status for task in planned.tasks] == ["scheduled", "scheduled"]
    assert "共享资源：小林" in draft.tasks[1].parallel_reason
    assert [(task.scheduled_start, task.scheduled_end) for task in planned.tasks] == [
        ("19:00", "20:00"),
        ("20:00", "21:00"),
    ]


def test_schedule_agent_exposes_an_inspectable_tool_call_workflow():
    analysis = ScriptAnalysisAgent().run(
        title="工具调用测试",
        version_label="v1",
        script_text="第一场\n小林：我们开始。\n第二场\n小林：继续。",
        script_id="tool-workflow",
        analysis_mode="rules",
    ).model_copy(update={"review_status": "confirmed"})

    agent = RehearsalScheduleAgent()
    draft = agent.run(analysis, default_minutes=45)
    assert [call.tool_name for call in draft.tool_calls] == [
        "inspect_script",
        "extract_scene_requirements",
        "extract_scene_requirements",
        "group_parallel_tasks",
        "validate_schedule_draft",
    ]
    assert draft.tool_calls[0].result["review_gate"] == "passed"
    assert draft.tool_calls[1].result["required_characters"] == ["小林"]

    planned = agent.assign(draft, [
        AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00"),
    ])
    assert [call.tool_name for call in planned.tool_calls[-3:]] == [
        "find_common_actor_slot",
        "find_common_actor_slot",
        "validate_schedule",
    ]
    assert planned.tool_calls[-1].result == {
        "scheduled_count": 2,
        "unassigned_count": 0,
        "overlap_count": 0,
    }
    linked_draft = agent.run(analysis, default_minutes=45, agent_run_id="1" * 32, root_run_id="1" * 32)
    linked_plan = agent.assign(
        linked_draft,
        [AvailabilitySlot(actor="小林", date="2026-08-25", start="19:00", end="21:00")],
        agent_run_id="2" * 32,
        parent_run_id=linked_draft.agent_run_id,
        root_run_id=linked_draft.root_run_id,
    )
    assert linked_draft.agent_run_id == "1" * 32
    assert linked_plan.agent_run_id == "2" * 32
    assert linked_plan.parent_run_id == "1" * 32
    assert linked_plan.root_run_id == "1" * 32


def test_schedule_agent_captures_music_and_budget_context():
    analysis = ScriptAnalysisAgent().run(
        title="资源上下文测试",
        version_label="v1",
        script_text="第一场\n小林：音乐进。\n导演：开始。",
        script_id="resource-context",
        analysis_mode="rules",
    ).model_copy(update={"review_status": "confirmed"})

    draft = RehearsalScheduleAgent().run(
        analysis,
        music_notes=[MusicTimelineNote(
            track_name="低频脉冲",
            scene_id="scene-1",
            cue_type="cue",
            start_seconds=12,
            note="灯暗后两拍进",
        )],
        budget_items=[BudgetLineItem(
            category="music",
            name="配乐授权",
            estimated_amount=100,
            actual_amount=120,
            status="committed",
        )],
        invoices=[InvoiceRecord(
            supplier="奇点文化",
            invoice_date="2026-08-25",
            category="music",
            amount=80,
            budget_item_id="missing-budget-item",
            status="pending",
        )],
    )

    assert draft.resource_context is not None
    assert len(draft.resource_context.music_cues) == 1
    assert len(draft.resource_context.budget_items) == 1
    assert draft.resource_context.estimated_total == 100
    assert draft.resource_context.actual_total == 120
    assert len(draft.resource_context.invoices) == 1
    assert draft.resource_context.invoice_total == 80
    assert draft.resource_context.verified_invoice_total == 0
    assert draft.resource_context.unlinked_invoice_count == 1
    assert "超出预算" in draft.resource_context.warnings[0]
    assert any("未关联预算项目" in warning for warning in draft.resource_context.warnings)
    resource_calls = [call for call in draft.tool_calls if call.tool_name == "inspect_rehearsal_resources"]
    assert len(resource_calls) == 1
    assert resource_calls[0].result == {
        "music_cue_count": 1,
        "budget_item_count": 1,
        "invoice_count": 1,
        "budget_variance": 20,
        "invoice_total": 80,
        "verified_invoice_total": 0,
        "unlinked_invoice_count": 1,
        "warning_count": 3,
    }


def test_line_reading_follows_selected_role_and_source_lines():
    analysis = ScriptAnalysisAgent().run(
        title="对词测试",
        version_label="v1",
        script_text="第一场\n导演：先看着我。\n小林：我准备好了。\n导演：那就开始。",
    )
    agent = LineReadingAgent()

    first = agent.respond(analysis, LineReadingRequest(
        scene_id="scene-1",
        character="小林",
        line_index=0,
    ))
    assert first.assistant_turns[0].character == "导演"
    assert first.assistant_turns[0].source_line == 2
    assert first.actor_prompt is not None
    assert first.actor_prompt.text == "我准备好了。"
    assert first.next_line_index == 1

    second = agent.respond(analysis, LineReadingRequest(
        scene_id="scene-1",
        character="小林",
        line_index=1,
        user_text="我准备好了。",
    ))
    assert second.feedback == "原词准确，继续下一句。"
    assert second.assistant_turns[0].text == "那就开始。"
    assert second.finished is True


def test_line_reading_adaptive_mode_degrades_to_original_line_without_llm():
    analysis = ScriptAnalysisAgent().run(
        title="降级对词",
        version_label="v1",
        script_text="第一场\n导演：你终于来了。\n小林：我一直在这里。",
    )

    response = LineReadingAgent().respond(analysis, LineReadingRequest(
        scene_id="scene-1",
        character="小林",
        mode="adaptive",
        line_index=0,
    ))

    assert response.engine == "fallback"
    assert response.assistant_turns[0].text == "你终于来了。"
    assert "回退到原词" in response.note


def test_line_reading_session_agent_persists_cursor_transcript_and_ignores_stale_index():
    analysis = ScriptAnalysisAgent().run(
        title="会话对词",
        version_label="v1",
        script_text="第一场\n导演：准备。\n小林：我来了。\n导演：开始。",
        script_id="line-session",
        analysis_mode="rules",
    )
    agent = LineReadingSessionAgent()

    first, session = agent.advance(
        analysis,
        LineReadingRequest(scene_id="scene-1", character="小林", mode="strict"),
    )
    assert first.session_id == session.session_id
    assert first.turn_count == 1
    assert session.line_index == 1
    assert session.actor_prompt is not None
    assert session.transcript[0].kind == "partner"

    second, finished = agent.advance(
        analysis,
        LineReadingRequest(
            scene_id="scene-1",
            character="小林",
            mode="strict",
            line_index=99,
            user_text="我来了。",
            session_id=session.session_id,
        ),
        session=session,
    )
    assert second.finished is True
    assert finished.line_index == 3
    assert finished.turn_count == 2
    assert [item.kind for item in finished.transcript] == ["partner", "actor", "partner", "feedback"]
    assert second.transcript == finished.transcript


def test_line_reading_session_keeps_role_profile_and_context_memory_stable():
    analysis = ScriptAnalysisAgent().run(
        title="带上下文的对词",
        version_label="v1",
        script_text="第一场\n导演：先别急着解释。\n小林：我知道了。\n导演：把信留下。",
        script_id="line-profile",
        analysis_mode="rules",
    )
    prompts = []

    def invoke(messages):
        prompts.append(messages[-1]["content"])
        return '{"turns":[{"character":"导演","text":"先别急着解释。"}],"note":"保留停顿。"}'

    fake_llm = SimpleNamespace(last_attempts=1, invoke=invoke)
    request_kwargs = {
        "scene_id": "scene-1",
        "character": "小林",
        "mode": "adaptive",
        "role_tone": "restrained",
        "context_note": "这一轮只练习句尾停顿。",
    }

    with patch("backend.rehearsal.line_reading.get_llm", return_value=fake_llm):
        agent = LineReadingSessionAgent()
        first, session = agent.advance(analysis, LineReadingRequest(**request_kwargs))
        second, resumed = agent.advance(
            analysis,
            LineReadingRequest(**request_kwargs, line_index=99, user_text="我知道了。", session_id=session.session_id),
            session=session,
        )

    assert first.role_tone == resumed.role_tone == session.role_tone == "restrained"
    assert resumed.context_note == session.context_note == "这一轮只练习句尾停顿。"
    assert "角色语气约束：克制（restrained）" in prompts[-1]
    assert "这一轮只练习句尾停顿。" in prompts[-1]
    assert "先别急着解释。" in prompts[-1]
    assert second.engine == "llm"

    with patch("backend.rehearsal.line_reading.get_llm", return_value=fake_llm):
        try:
            agent.advance(
                analysis,
                LineReadingRequest(**{**request_kwargs, "role_tone": "urgent", "session_id": session.session_id}),
                session=session,
            )
        except ValueError as exc:
            assert "角色语气或排练上下文已变化" in str(exc)
        else:
            raise AssertionError("changing the role profile must restart the session")


def test_rehearsal_mirror_keeps_raw_notes_and_structures_feedback_without_llm():
    request = RehearsalFeedbackRequest(
        rehearsal_date="2026-08-25",
        participants=["导演", "小林", "小林"],
        outputs=["完成第一场走位"],
        notes="小林第二段情绪已经清晰。\n换位时还是会忘词，道具组缺少备用手电筒。",
    )

    response = RehearsalMirrorAgent().summarize(
        request,
        record_id="a" * 32,
        script_title="轨道之外",
        scene_title="第一场",
    )

    assert response.engine == "fallback"
    assert response.notes == request.notes
    assert response.participants == ["导演", "小林"]
    assert response.outputs == ["完成第一场走位"]
    assert response.strengths == ["小林第二段情绪已经清晰。"]
    assert len(response.blockers) == 1
    assert response.next_actions[0].startswith("下次排练复核：")


def test_rehearsal_feedback_rejects_invalid_date_and_empty_notes():
    invalid_values = [
        {"rehearsal_date": "2026-02-30", "notes": "有记录"},
        {"rehearsal_date": "2026-08-25", "notes": "   "},
    ]
    for values in invalid_values:
        try:
            RehearsalFeedbackRequest(**values)
        except ValidationError:
            continue
        raise AssertionError(f"invalid rehearsal feedback should be rejected: {values}")


def test_rehearsal_metrics_counts_outputs_blockers_and_excludes_records_outside_window():
    mirror = RehearsalMirrorAgent()
    recent = mirror.summarize(
        RehearsalFeedbackRequest(
            rehearsal_date="2026-08-25",
            participants=["导演", "小林"],
            outputs=["完成第一场走位"],
            notes="小林忘词，需要再读两遍。",
            analysis_mode="rules",
        ),
        record_id="m" * 32,
    )
    smooth = mirror.summarize(
        RehearsalFeedbackRequest(
            rehearsal_date="2026-08-24",
            participants=["导演", "小林", "许教授"],
            notes="本次排练顺利，节奏稳定。",
            analysis_mode="rules",
        ),
        record_id="n" * 32,
    )
    outside_window = mirror.summarize(
        RehearsalFeedbackRequest(
            rehearsal_date="2026-08-10",
            participants=["导演"],
            outputs=["旧记录"],
            notes="旧反馈。",
            analysis_mode="rules",
        ),
        record_id="o" * 32,
    )

    metrics = RehearsalMetricsAgent().summarize(
        [recent, smooth, outside_window],
        window_days=7,
        as_of=date(2026, 8, 25),
    )

    assert metrics.session_count == 2
    assert metrics.output_count == 1
    assert metrics.sessions_with_outputs == 1
    assert metrics.sessions_with_blockers == 1
    assert metrics.output_coverage == 50.0
    assert metrics.blocker_rate == 50.0
    assert metrics.unique_participant_count == 3
    assert metrics.average_participants == 2.5
    assert metrics.engine_counts == {"rules": 2}
    assert metrics.top_blockers[0].label == "小林忘词，需要再读两遍。"
    assert len(metrics.trend) == 7
    assert metrics.recent_sessions[0].record_id == "m" * 32


def test_rehearsal_metrics_empty_window_returns_zero_rates_and_a_full_trend():
    metrics = RehearsalMetricsAgent().summarize(
        [],
        window_days=7,
        as_of=date(2026, 8, 25),
    )

    assert metrics.session_count == 0
    assert metrics.output_coverage == 0.0
    assert metrics.blocker_rate == 0.0
    assert metrics.next_action_rate == 0.0
    assert len(metrics.trend) == 7
    assert all(item.sessions == 0 for item in metrics.trend)


def test_script_version_diff_marks_scene_line_and_actor_changes():
    parser = ScriptAnalysisAgent()
    previous = parser.run(
        title="轨道之外",
        version_label="v1",
        script_text="第一场\n导演：准备。\n小林：我来了。",
    )
    current = parser.run(
        title="轨道之外",
        version_label="v2",
        script_text="第一场 走廊\n导演：准备，进来。\n小林：我来了。\n（小林拿起手电筒。）\n许教授：等等。\n第二场\n小林：下一场。",
    )

    diff = ScriptVersionDiffAgent().compare(previous, current)

    assert diff.added_scene_count == 1
    assert diff.removed_scene_count == 0
    assert diff.changed_scene_count == 1
    first_scene = diff.scenes[0]
    assert first_scene.status == "changed"
    assert first_scene.new_title == "走廊"
    assert first_scene.added_characters == ["许教授"]
    assert first_scene.added_props == ["手电筒"]
    assert {change.change_type for change in first_scene.line_changes} == {"modified", "added"}
    assert "新增演员：许教授" in first_scene.impact
    assert "需重新核对台词：导演、许教授" in first_scene.impact
    assert diff.requires_schedule_review is True
    assert diff.requires_line_reading_review is True
    assert diff.requires_resource_review is True
    assert {item.impact_type for item in diff.downstream_impacts} == {"schedule", "line-reading", "resource"}
    schedule_impact = next(item for item in diff.downstream_impacts if item.impact_type == "schedule")
    assert schedule_impact.scene_number == 1
    assert schedule_impact.severity == "high"
    assert "演员档期" in schedule_impact.action
    resource_impact = next(item for item in diff.downstream_impacts if item.impact_type == "resource")
    assert resource_impact.affected_props == ["手电筒"]


def test_script_version_diff_reports_identical_versions_without_changes():
    analysis = ScriptAnalysisAgent().run(
        title="稳定版本",
        version_label="v1",
        script_text="第一场\n小林：从头来一遍。",
    )

    diff = ScriptVersionDiffAgent().compare(analysis, analysis)

    assert diff.summary == "两个剧本版本的场次、角色、道具和台词没有检测到变化。"
    assert diff.unchanged_scene_count == 1
    assert diff.scenes[0].status == "unchanged"
    assert diff.downstream_impacts == []
    assert diff.requires_schedule_review is False
    assert diff.requires_line_reading_review is False
    assert diff.requires_resource_review is False


def test_script_version_diff_marks_line_only_change_without_resource_review():
    parser = ScriptAnalysisAgent()
    previous = parser.run(
        title="台词测试",
        version_label="v1",
        script_text="第一场\n小林：再来一遍。",
    )
    current = parser.run(
        title="台词测试",
        version_label="v2",
        script_text="第一场\n小林：我们再来一遍。",
    )

    diff = ScriptVersionDiffAgent().compare(previous, current)

    assert diff.requires_schedule_review is True
    assert diff.requires_line_reading_review is True
    assert diff.requires_resource_review is False
    assert [item.impact_type for item in diff.downstream_impacts] == ["schedule", "line-reading"]
    assert diff.downstream_impacts[1].affected_characters == ["小林"]


def test_stage_agent_keeps_stage_direction_source_and_builds_actor_prop_events():
    analysis = ScriptAnalysisAgent().run(
        title="舞台测试",
        version_label="v1",
        script_text="第一场\n（小林从舞台左侧上场，拿起椅子。）\n导演：先站到中央。\n（导演下场。）",
    )

    scene = analysis.scenes[0]
    assert scene.stage_directions[0].source_line == 2
    assert scene.stage_directions[0].kind == "entrance"

    view = StageVisualizationAgent().render(analysis, scene.scene_id)
    actor = next(item for item in view.actors if item.name == "小林")
    prop = next(item for item in view.props if item.name == "椅子")

    assert actor.status == "onstage"
    assert actor.position == "center_left"
    assert prop.position == "center_left"
    assert view.events[0].event_type == "entrance"
    assert any(event.event_type == "prop" for event in view.events)
    assert any(event.event_type == "exit" for event in view.events)


def test_resource_agent_explains_ready_maintenance_and_missing_props():
    analysis = ScriptAnalysis(
        script_id="resource-script",
        title="资源测试",
        version_label="v1",
        scenes=[Scene(
            scene_id="scene-1",
            number=1,
            title="第一场",
            props=["椅子", "手电筒", "信封"],
            source=SourceSpan(start_line=1, end_line=4),
        )],
        created_at="2026-08-25T00:00:00Z",
    )
    result = ResourceAgent().check(analysis, [
        ResourceInventoryItem(resource_id="a" * 32, category="prop", name="椅子", quantity=1),
        ResourceInventoryItem(resource_id="b" * 32, category="prop", name="手电筒", quantity=1, status="maintenance"),
    ], scene_id="scene-1")

    statuses = {item.name: item.status for item in result.requirements}
    assert statuses == {"椅子": "ready", "手电筒": "maintenance", "信封": "missing"}
    assert result.ready_count == 1
    assert result.missing_count == 2
    assert "没有匹配记录" in next(item.note for item in result.requirements if item.name == "信封")


def test_resource_audit_agent_explains_created_updated_and_unchanged_records():
    before = [
        ResourceInventoryItem(resource_id="a" * 32, category="prop", name="椅子", quantity=1),
    ]
    after = [
        ResourceInventoryItem(resource_id="a" * 32, category="prop", name="椅子", quantity=2),
        ResourceInventoryItem(resource_id="b" * 32, category="prop", name="手电筒", quantity=1),
    ]

    audit = ResourceAuditAgent().compare(
        resource_type="inventory",
        operation="replace",
        before=before,
        after=after,
    )

    assert isinstance(audit, ResourceAuditRecord)
    assert audit.changed_count == 2
    assert audit.summary == "库存变更：新增 1 条、修改 1 条。"
    assert {item.change_type for item in audit.changes} == {"created", "updated"}
    updated = next(item for item in audit.changes if item.change_type == "updated")
    assert updated.label == "椅子"
    assert updated.changed_fields == ["数量"]
    assert ResourceAuditAgent().compare(
        resource_type="inventory",
        operation="replace",
        before=after,
        after=after,
    ) is None


def test_version_diff_links_matching_user_resource_audits_to_resource_impacts():
    parser = ScriptAnalysisAgent()
    previous = parser.run(
        title="轨道之外",
        version_label="v1",
        script_text="第一场\n小林：我来了。",
    )
    current = parser.run(
        title="轨道之外",
        version_label="v2",
        script_text="第一场\n小林：我来了。\n（小林拿起手电筒。）",
    )
    diff = ScriptVersionDiffAgent().compare(previous, current)
    audit = ResourceAuditAgent().compare(
        resource_type="inventory",
        operation="replace",
        before=[],
        after=[ResourceInventoryItem(resource_id="a" * 32, category="prop", name="手电筒")],
    )

    assert audit is not None
    enriched = attach_resource_audit_matches(diff, [audit])
    resource_impact = next(item for item in enriched.downstream_impacts if item.impact_type == "resource")
    assert len(resource_impact.resource_audit_matches) == 1
    assert resource_impact.resource_audit_matches[0].label == "手电筒"
    assert resource_impact.resource_audit_matches[0].audit_id == audit.audit_id


def test_agent_run_metrics_aggregates_status_and_failed_trace_steps():
    records = [
        AgentRunRecord(
            run_id="a" * 32,
            agent="script-analysis",
            action="解析",
            summary="完成",
            trace=[AgentStep(name="校验", status="completed", summary="完成")],
            duration_ms=100,
            created_at="2026-08-20T10:00:00+00:00",
        ),
        AgentRunRecord(
            run_id="b" * 32,
            agent="line-reading",
            action="对词",
            status="fallback",
            summary="降级",
            trace=[AgentStep(name="选择策略", status="repaired", summary="回退")],
            duration_ms=200,
            created_at="2026-08-21T10:00:00+00:00",
        ),
        AgentRunRecord(
            run_id="c" * 32,
            agent="resource-check",
            action="检查资源",
            status="failed",
            summary="失败",
            trace=[AgentStep(name="匹配库存", status="failed", summary="库存文件读取失败")],
            duration_ms=400,
            created_at="2026-08-22T10:00:00+00:00",
        ),
        AgentRunRecord(
            run_id="d" * 32,
            agent="resource-check",
            action="旧检查",
            status="failed",
            summary="窗口外",
            trace=[AgentStep(name="匹配库存", status="failed", summary="不应计入")],
            duration_ms=900,
            created_at="2026-07-01T10:00:00+00:00",
        ),
    ]

    metrics = AgentRunMetricsAgent().summarize(
        records,
        window_days=30,
        as_of=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert metrics.total_runs == 3
    assert metrics.completed_runs == 1
    assert metrics.fallback_runs == 1
    assert metrics.failed_runs == 1
    assert metrics.failure_rate == 33.3
    assert metrics.fallback_rate == 33.3
    assert metrics.average_duration_ms == 233
    assert metrics.failed_steps[0].name == "匹配库存"
    assert metrics.failed_steps[0].failed_count == 1


def test_llm_provider_retries_transient_errors_with_a_two_attempt_budget():
    calls = {"count": 0}

    class TemporaryProviderError(Exception):
        status_code = 503

    def create_completion(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TemporaryProviderError("temporary outage")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion)),
    )
    with patch("backend.llm_provider.OpenAI", return_value=fake_client), patch("backend.llm_provider.time.sleep") as sleep:
        llm = ChatLLM("demo", "key", "https://example.test/v1", 0.0)
        assert llm.invoke([{ "role": "user", "content": "ping" }]) == "ok"

    assert calls["count"] == 2
    assert llm.last_attempts == 2
    sleep.assert_called_once()


def test_resource_models_reject_invalid_booking_and_conflict_only_when_intervals_overlap():
    invalid_values = [
        {"room_name": "排练室 A", "date": "2026-02-30", "start": "19:00", "end": "20:00"},
        {"room_name": "排练室 A", "date": "2026-08-25", "start": "20:00", "end": "20:00"},
        {"room_name": "排练室 A", "date": "2026-08-25", "start": "25:00", "end": "26:00"},
    ]
    for values in invalid_values:
        try:
            RoomBookingRequest(**values)
        except ValidationError:
            continue
        raise AssertionError(f"invalid room booking should be rejected: {values}")

    existing = RoomBooking(
        booking_id="c" * 32,
        room_name="排练室 A",
        date="2026-08-25",
        start="19:00",
        end="20:00",
        purpose="第一场",
    )
    assert room_booking_conflicts(RoomBookingRequest(
        room_name="排练室 A", date="2026-08-25", start="19:30", end="20:30",
    ), existing)
    assert not room_booking_conflicts(RoomBookingRequest(
        room_name="排练室 A", date="2026-08-25", start="20:00", end="21:00",
    ), existing)
    assert not room_booking_conflicts(RoomBookingRequest(
        room_name="排练室 B", date="2026-08-25", start="19:30", end="20:30",
    ), existing)


def test_resource_finance_agent_separates_budget_actual_and_invoice_risk():
    music_item = BudgetLineItem(
        budget_item_id="a" * 32,
        category="music",
        name="原创配乐",
        estimated_amount=100,
        actual_amount=120,
        status="paid",
    )
    prop_item = BudgetLineItem(
        budget_item_id="b" * 32,
        category="prop",
        name="备用手电筒",
        estimated_amount=50,
        actual_amount=0,
        status="planned",
    )
    summary = ResourceFinanceAgent().summarize(
        [music_item, prop_item],
        [
            InvoiceRecord(
                invoice_id="c" * 32,
                supplier="声音工作室",
                invoice_date="2026-08-25",
                category="music",
                amount=80,
                budget_item_id=music_item.budget_item_id,
                status="verified",
            ),
            InvoiceRecord(
                invoice_id="d" * 32,
                supplier="临时供应商",
                invoice_date="2026-08-25",
                category="prop",
                amount=20,
                status="pending",
            ),
            InvoiceRecord(
                invoice_id="e" * 32,
                supplier="已驳回供应商",
                invoice_date="2026-08-25",
                category="other",
                amount=999,
                status="rejected",
            ),
        ],
    )

    assert summary.estimated_total == 150.0
    assert summary.actual_total == 120.0
    assert summary.invoice_total == 100.0
    assert summary.verified_invoice_total == 80.0
    assert summary.linked_invoice_total == 80.0
    assert summary.unlinked_invoice_total == 20.0
    assert summary.variance == -30.0
    assert any("未关联" in warning for warning in summary.warnings)
    assert any("待核验" in warning for warning in summary.warnings)
    assert {item.category for item in summary.categories} == {"music", "prop"}

    try:
        MusicTimelineNote(track_name="转场", start_seconds=20, end_seconds=10)
    except ValidationError:
        pass
    else:
        raise AssertionError("music timeline should reject a reversed interval")


def test_logbook_agent_keeps_original_note_and_adds_context_tag():
    request = RehearsalLogRequest(
        script_id="script-1",
        scene_id="scene-1",
        rehearsal_date="2026-08-25",
        author="场记小周",
        category="blocking",
        content="小林从台口回到中央时停顿两拍。",
        tags=["节奏", "节奏"],
        source_line=28,
    )

    record = RehearsalLogAgent().record(
        request,
        log_id="d" * 32,
        script_title="轨道之外",
        scene_title="第一场",
    )

    assert record.content == request.content
    assert record.script_title == "轨道之外"
    assert record.scene_title == "第一场"
    assert record.tags == ["走位", "节奏"]
    assert record.source_line == 28


def test_logbook_request_rejects_invalid_date_and_empty_content():
    invalid_values = [
        {"rehearsal_date": "2026-02-30", "content": "有记录"},
        {"rehearsal_date": "2026-08-25", "content": "   "},
    ]
    for values in invalid_values:
        try:
            RehearsalLogRequest(**values)
        except ValidationError:
            continue
        raise AssertionError(f"invalid logbook request should be rejected: {values}")


def test_suggestion_agent_preserves_content_marks_safety_and_supports_status_response():
    request = SuggestionRequest(
        script_id="script-1",
        scene_id="scene-1",
        actor_name="小林",
        category="safety",
        content="椅子边缘有松动，继续走位可能导致受伤。",
    )
    agent = SuggestionInboxAgent()
    suggestion = agent.submit(
        request,
        suggestion_id="e" * 32,
        script_title="轨道之外",
        scene_title="第一场",
    )

    assert suggestion.content == request.content
    assert suggestion.priority == "high"
    assert suggestion.status == "new"

    updated = agent.update(suggestion, SuggestionUpdateRequest(
        status="accepted",
        response="已更换椅子并在下一次排练前复查。",
    ))
    assert updated.status == "accepted"
    assert updated.response.startswith("已更换")
    assert updated.updated_at >= suggestion.updated_at


def test_suggestion_request_rejects_empty_actor_or_content():
    invalid_values = [
        {"actor_name": "", "content": "有建议"},
        {"actor_name": "小林", "content": "   "},
    ]
    for values in invalid_values:
        try:
            SuggestionRequest(**values)
        except ValidationError:
            continue
        raise AssertionError(f"invalid suggestion should be rejected: {values}")


def test_motto_agent_preserves_quote_and_adds_explainable_theme_tag():
    request = MottoRequest(
        script_id="script-1",
        scene_id="scene-1",
        text="  先让角色抵达，再让台词发生。  ",
        author="导演",
        source="第一场排练",
        theme="performance",
        tags=["呼吸", "呼吸"],
    )

    motto = MottoAgent().record(
        request,
        motto_id="f" * 32,
        script_title="轨道之外",
        scene_title="第一场",
    )

    assert motto.text == "先让角色抵达，再让台词发生。"
    assert motto.tags == ["表演", "呼吸"]
    assert motto.script_title == "轨道之外"
    assert motto.scene_title == "第一场"

    updated = MottoAgent().update(motto, MottoUpdateRequest(favorite=True))
    assert updated.favorite is True
    assert updated.text == motto.text
    assert updated.updated_at >= motto.updated_at


def test_motto_request_rejects_blank_quote():
    try:
        MottoRequest(text="   ")
    except ValidationError:
        return
    raise AssertionError("blank motto text should be rejected")


def test_promo_agent_rules_mode_is_deterministic_without_llm():
    request = PromoCopyRequest(
        script_id="script-1",
        work_title="轨道之外",
        audience="festival",
        tone="poetic",
        brief="突出排练中的身体关系，不透露剧情结局。",
        analysis_mode="rules",
    )

    copy = PromoCopyAgent().generate(
        request,
        copy_id="a" * 32,
        script_title="轨道之外",
        scene_titles=["第一场", "第二场"],
        characters=["导演", "小林"],
    )

    assert copy.engine == "rules"
    assert copy.work_title == "轨道之外"
    assert "轨道之外" in copy.headline
    assert "第一场" in copy.short_copy
    assert "小林" in copy.long_copy
    assert copy.hashtags == ["#奇点剧团", "#轨道之外", "#话剧排练"]


def test_promo_request_normalizes_optional_brief_and_rejects_blank_title():
    request = PromoCopyRequest(work_title="  新作  ", brief="  身体排练  ")
    assert request.work_title == "新作"
    assert request.brief == "身体排练"

    try:
        PromoCopyRequest(work_title="   ")
    except ValidationError:
        return
    raise AssertionError("blank promo title should be rejected")


def test_script_rag_rules_returns_source_line_evidence_for_a_script_question():
    script = Path("docs/examples/qidian-demo-script.md").read_text(encoding="utf-8")
    analysis = ScriptAnalysisAgent().run(
        title="轨道之外",
        version_label="v1",
        script_text=script,
        script_id="rag-script",
        analysis_mode="rules",
    )

    response = ScriptRagAgent().answer(
        analysis,
        ScriptRagQueryRequest(question="第一场小林拿起了什么？", answer_mode="rules"),
    )

    assert response.engine == "rules"
    assert response.retrieval_engine == "rules"
    assert response.evidence
    assert any("手电筒" in item.text for item in response.evidence)
    assert all(item.source_line >= 1 for item in response.evidence)
    assert any(item.evidence_id in response.answer for item in response.evidence)


def test_script_rag_does_not_invent_an_answer_when_no_evidence_matches():
    analysis = ScriptAnalysisAgent().run(
        title="短场",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。",
        script_id="rag-empty-script",
        analysis_mode="rules",
    )

    response = ScriptRagAgent().answer(
        analysis,
        ScriptRagQueryRequest(question="火车站的灯光颜色是什么？", answer_mode="auto"),
        user_id="rag-user-without-provider",
    )

    assert response.evidence == []
    assert response.engine == "rules"
    assert "没有检索到" in response.answer


def test_script_rag_semantic_mode_falls_back_to_rules_without_embedding_config():
    analysis = ScriptAnalysisAgent().run(
        title="短场",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。",
        script_id="rag-fallback-script",
        analysis_mode="rules",
    )

    response = ScriptRagAgent().answer(
        analysis,
        ScriptRagQueryRequest(
            question="椅子在哪里？",
            retrieval_mode="semantic",
            answer_mode="rules",
        ),
        user_id="rag-user-without-provider",
    )

    assert response.retrieval_engine == "rules-fallback"
    assert response.evidence
    assert any("椅子" in item.text for item in response.evidence)


def test_rehearsal_demo_flow_connects_core_agents_without_provider_keys():
    script = Path("docs/examples/qidian-demo-script.md").read_text(encoding="utf-8")
    analysis = ScriptAnalysisAgent().run(
        title="轨道之外",
        version_label="demo",
        script_text=script,
        script_id="demo-script",
        analysis_mode="rules",
    )
    reviewed = analysis.model_copy(update={"review_status": "confirmed"})

    draft = RehearsalScheduleAgent().run(reviewed, default_minutes=45)
    assert len(draft.tasks) == 2
    slots = [
        AvailabilitySlot(actor=actor, date="2026-08-25", start="19:00", end="21:00")
        for actor in ["导演", "小林", "许教授", "小周"]
    ]
    planned = RehearsalScheduleAgent().assign(draft, slots)
    assert all(task.status == "scheduled" for task in planned.tasks)
    assert planned.tasks[0].scheduled_end == planned.tasks[1].scheduled_start

    first_scene = reviewed.scenes[0]
    line_reading = LineReadingAgent().respond(
        reviewed,
        LineReadingRequest(scene_id=first_scene.scene_id, character="小林", mode="strict"),
    )
    assert line_reading.engine == "strict"
    assert line_reading.assistant_turns[0].character == "导演"
    assert line_reading.actor_prompt is not None
    assert line_reading.actor_prompt.source_line >= 1

    stage = StageVisualizationAgent().render(reviewed, first_scene.scene_id)
    assert any(event.event_type == "dialogue" for event in stage.events)
    assert all(event.source_line >= 1 for event in stage.events)

    resources = ResourceAgent().check(
        reviewed,
        [ResourceInventoryItem(category="prop", name="椅子", quantity=1)],
        scene_id=first_scene.scene_id,
    )
    assert any(item.name == "椅子" and item.status == "ready" for item in resources.requirements)

    feedback = RehearsalMirrorAgent().summarize(
        RehearsalFeedbackRequest(
            rehearsal_date="2026-08-25",
            participants=["导演", "小林"],
            outputs=["完成第一场走位"],
            notes="椅子位置已确定。小林忘词，需要再读两遍。",
            analysis_mode="rules",
        ),
        record_id="b" * 32,
    )
    assert feedback.engine == "rules"
    assert "小林忘词" in feedback.blockers[0]

    log = RehearsalLogAgent().record(
        RehearsalLogRequest(
            rehearsal_date="2026-08-25",
            author="场记",
            category="blocking",
            content="椅子位置已确定。",
        ),
        log_id="c" * 32,
    )
    assert log.content == "椅子位置已确定。"
    assert "走位" in log.tags

    suggestion = SuggestionInboxAgent().submit(
        SuggestionRequest(actor_name="小林", category="safety", content="椅子边缘有松动。"),
        suggestion_id="d" * 32,
    )
    assert suggestion.priority == "high"

    motto = MottoAgent().record(
        MottoRequest(text="先让角色抵达，再让台词发生。", theme="performance"),
        motto_id="e" * 32,
    )
    assert motto.text == "先让角色抵达，再让台词发生。"

    promo = PromoCopyAgent().generate(
        PromoCopyRequest(work_title="轨道之外", analysis_mode="rules"),
        copy_id="f" * 32,
        script_title=reviewed.title,
        scene_titles=[scene.title for scene in reviewed.scenes],
        characters=[character.name for character in reviewed.characters],
    )
    assert promo.engine == "rules"
    assert "轨道之外" in promo.headline


def test_agent_run_record_is_user_scoped_and_preserves_explainable_trace():
    original_base_dir = settings.base_dir
    with TemporaryDirectory() as temp_dir:
        try:
            settings.base_dir = Path(temp_dir)
            record = record_agent_run(
                user_id="actor-a",
                agent="script-rag",
                action="剧本证据问答",
                script_id="a" * 32,
                script_title="轨道之外",
                mode="检索:rules / 回答:rules",
                summary="返回 1 条可核对证据。",
                trace=[AgentStep(
                    name="检索相关证据",
                    status="completed",
                    summary="命中原文第 3 行。",
                    output_count=1,
                )],
                warnings=[],
                status=outcome_status(engine="rules"),
                duration_ms=12,
            )

            restored = get_agent_run(record.run_id, user_id="actor-a")
            assert restored is not None
            assert restored.trace[0].output_count == 1
            assert restored.script_title == "轨道之外"
            assert restored.parent_run_id is None
            assert restored.root_run_id == record.run_id
            assert get_agent_run(record.run_id, user_id="actor-b") is None
            assert [item.run_id for item in list_agent_runs(user_id="actor-a")] == [record.run_id]

            child = record_agent_run(
                user_id="actor-a",
                agent="schedule-plan",
                action="匹配演员档期",
                script_id="a" * 32,
                script_title="轨道之外",
                mode="共同空闲时间匹配",
                summary="完成排班。",
                trace=[],
                parent_run_id=record.run_id,
                root_run_id=record.root_run_id,
                run_id="b" * 32,
            )
            assert child.parent_run_id == record.run_id
            assert child.root_run_id == record.run_id
            assert [item.run_id for item in list_agent_runs(user_id="actor-a")] == [child.run_id, record.run_id]
        finally:
            settings.base_dir = original_base_dir


def test_resource_audit_storage_is_user_scoped_and_keeps_latest_first():
    original_base_dir = settings.base_dir
    with TemporaryDirectory() as temp_dir:
        try:
            settings.base_dir = Path(temp_dir)
            audit = ResourceAuditAgent().compare(
                resource_type="inventory",
                operation="replace",
                before=[],
                after=[ResourceInventoryItem(resource_id="a" * 32, category="prop", name="椅子")],
            )
            second_audit = ResourceAuditAgent().compare(
                resource_type="inventory",
                operation="replace",
                before=[],
                after=[ResourceInventoryItem(resource_id="b" * 32, category="prop", name="手电筒")],
            )
            assert audit is not None
            assert second_audit is not None
            save_resource_audit(audit, user_id="actor-a")
            save_resource_audit(second_audit, user_id="actor-a")

            assert [item.audit_id for item in list_resource_audits(user_id="actor-a")] == [second_audit.audit_id, audit.audit_id]
            assert [item.audit_id for item in list_resource_audits(user_id="actor-a", query="手电筒")] == [second_audit.audit_id]
            assert [item.audit_id for item in list_resource_audits(user_id="actor-a", resource_type="inventory", change_type="created")] == [second_audit.audit_id, audit.audit_id]
            assert list_resource_audits(user_id="actor-b") == []
        finally:
            settings.base_dir = original_base_dir


def test_rehearsal_agent_eval_set_is_reproducible_without_provider_keys():
    from evals.run_rehearsal_evals import evaluate_cases

    report = evaluate_cases()

    assert report["total"] == 11
    assert report["failed"] == 0
    assert report["pass_rate"] == 100.0
