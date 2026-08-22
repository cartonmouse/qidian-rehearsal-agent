"""对词 Agent：以原始台词为锚点推进角色练习，并支持 LLM 适应性回应。"""

from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.llm_provider import HumanMessage, SystemMessage, get_llm
from backend.rehearsal.models import (
    DialogueLine,
    LineReadingRequest,
    LineReadingResponse,
    LineReadingSession,
    LineReadingTranscriptItem,
    LineReadingTurn,
    ScriptAnalysis,
)


logger = logging.getLogger("uvicorn")


class _AdaptiveTurn(BaseModel):
    character: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)


class _AdaptiveResponse(BaseModel):
    turns: list[_AdaptiveTurn] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=500)


_ADAPTIVE_SYSTEM_PROMPT = """你是话剧排练中的对词搭档。
你必须以给定剧本台词为事实锚点，只扮演非练习者角色，帮助练习者顺着剧情继续排练。
只输出一个 JSON 对象，不要输出 Markdown 或解释，格式为：
{"turns":[{"character":"角色名","text":"回应台词"}],"note":"一句简短排练提示"}

要求：
1. turns 的数量和输入的参考台词数量完全一致，character 必须逐项保持一致。
2. 默认保留原台词的情节事实、人物关系和行动意图，只允许为了回应练习者的临场表达而做自然、克制的口语调整。
3. 不要替练习者说话，不要增加剧本没有的关键事实，不要改写成剧情总结。
4. 如果练习者没有偏离原意，优先返回接近原台词的自然表达。
"""


def _load_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate
        if candidate.endswith("```"):
            candidate = candidate[:-3].rstrip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response does not contain a JSON object")
        payload = json.loads(candidate[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


def _strict_feedback(expected: str, actual: str) -> str:
    expected_normalized = _normalize_text(expected)
    actual_normalized = _normalize_text(actual)
    if expected_normalized == actual_normalized:
        return "原词准确，继续下一句。"
    similarity = difflib.SequenceMatcher(None, expected_normalized, actual_normalized).ratio()
    if similarity >= 0.72:
        return "台词基本一致，可以继续；需要时再回看原词。"
    return "这句与原词差异较大，系统仍继续推进，你可以稍后回读原句。"


class LineReadingAgent:
    """Advance a stateless rehearsal turn.

    The frontend keeps the current line index. The backend always derives the
    next cue from the stored script, so adaptive LLM output cannot replace the
    source dialogue or move the session to an arbitrary line.
    """

    def respond(
        self,
        analysis: ScriptAnalysis,
        request: LineReadingRequest,
        *,
        user_id: str | None = None,
    ) -> LineReadingResponse:
        scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
        if scene is None:
            raise ValueError("对词场次不存在")

        role = request.character.strip()
        roles = {line.character for line in scene.lines}
        if role not in roles:
            raise ValueError("当前场次没有所选角色的可练习台词")

        lines = scene.lines
        index = request.line_index
        if index > len(lines):
            raise ValueError("对词进度无效，请重新开始当前场次")

        feedback = ""
        if request.user_text.strip():
            if index >= len(lines) or lines[index].character != role:
                raise ValueError("当前不是所选角色的台词，请先跟随场次提示")
            expected = lines[index]
            feedback = (
                _strict_feedback(expected.text, request.user_text)
                if request.mode == "strict"
                else "已记录你的临场表达，按剧情意图继续下一句。"
            )
            index += 1

        partner_lines: list[DialogueLine] = []
        while index < len(lines) and lines[index].character != role:
            partner_lines.append(lines[index])
            index += 1

        engine = "strict"
        turns = [
            LineReadingTurn(
                character=line.character,
                text=line.text,
                source_line=line.source.start_line,
            )
            for line in partner_lines
        ]
        note = ""
        if partner_lines and request.mode == "adaptive":
            try:
                turns, note = self._adapt_turns(
                    partner_lines,
                    role=role,
                    user_text=request.user_text.strip(),
                    user_id=user_id,
                )
                engine = "llm"
            except Exception as exc:  # noqa: BLE001 - LLM is an optional branch
                logger.warning("Line reading LLM fallback: %s", exc)
                engine = "fallback"
                note = "当前未使用 LLM，已回退到原词，仍可继续排练。"

        actor_prompt = None
        if index < len(lines) and lines[index].character == role:
            line = lines[index]
            actor_prompt = LineReadingTurn(
                character=line.character,
                text=line.text,
                source_line=line.source.start_line,
            )

        finished = index >= len(lines)
        return LineReadingResponse(
            script_id=analysis.script_id,
            scene_id=scene.scene_id,
            scene_title=scene.title,
            character=role,
            mode=request.mode,
            engine=engine,
            next_line_index=None if finished else index,
            assistant_turns=turns,
            actor_prompt=actor_prompt,
            feedback=feedback,
            note=note,
            finished=finished,
        )

    def _adapt_turns(
        self,
        lines: list[DialogueLine],
        *,
        role: str,
        user_text: str,
        user_id: str | None,
    ) -> tuple[list[LineReadingTurn], str]:
        source_turns = [
            {"character": line.character, "text": line.text}
            for line in lines
        ]
        llm = get_llm(user_id)
        response = llm.invoke([
            SystemMessage(_ADAPTIVE_SYSTEM_PROMPT),
            HumanMessage(
                f"练习者角色：{role}\n"
                f"练习者刚才的表达：{user_text or '尚未开口'}\n"
                "请改写以下非练习者参考台词，并保持 turns 顺序和数量：\n"
                f"{json.dumps(source_turns, ensure_ascii=False)}"
            ),
        ])
        draft = _AdaptiveResponse.model_validate(_load_json(response))
        if len(draft.turns) != len(lines):
            raise ValueError("LLM returned an unexpected number of rehearsal turns")

        turns: list[LineReadingTurn] = []
        for line, item in zip(lines, draft.turns):
            if item.character.strip() != line.character:
                raise ValueError("LLM changed a rehearsal character")
            turns.append(LineReadingTurn(
                character=line.character,
                text=item.text.strip(),
                source_line=line.source.start_line,
            ))
        note = draft.note.strip()
        if llm.last_attempts > 1:
            retry_note = f"LLM 请求在第 {llm.last_attempts} 次尝试后成功。"
            note = f"{note} {retry_note}".strip()
        return turns, note[:500]


class LineReadingSessionAgent:
    """Persist the cursor and transcript around the stateless line-turn Agent."""

    def __init__(self, agent: LineReadingAgent | None = None):
        self.agent = agent or LineReadingAgent()

    def advance(
        self,
        analysis: ScriptAnalysis,
        request: LineReadingRequest,
        *,
        session: LineReadingSession | None = None,
        user_id: str | None = None,
    ) -> tuple[LineReadingResponse, LineReadingSession]:
        scene = next((item for item in analysis.scenes if item.scene_id == request.scene_id), None)
        if scene is None:
            raise ValueError("对词场次不存在")

        now = datetime.now(timezone.utc).isoformat()
        if session is not None:
            if (
                session.script_id != analysis.script_id
                or session.scene_id != request.scene_id
                or session.character != request.character.strip()
            ):
                raise ValueError("对词会话与当前剧本、场次或角色不匹配")
            if session.mode != request.mode:
                raise ValueError("对词会话模式已变化，请重新开始当前场次")
            line_index = session.line_index
            session_id = session.session_id
            created_at = session.created_at
            previous_transcript = list(session.transcript)
            previous_turn_count = session.turn_count
            engine_counts = dict(session.engine_counts)
        else:
            line_index = request.line_index
            session_id = uuid4().hex
            created_at = now
            previous_transcript = []
            previous_turn_count = 0
            engine_counts = {}

        effective_request = request.model_copy(update={
            "line_index": line_index,
            "session_id": session_id,
        })
        response = self.agent.respond(analysis, effective_request, user_id=user_id)

        additions: list[LineReadingTranscriptItem] = []
        if request.user_text.strip():
            source_line = (
                scene.lines[line_index].source.start_line
                if 0 <= line_index < len(scene.lines)
                else None
            )
            additions.append(LineReadingTranscriptItem(
                kind="actor",
                character=request.character.strip(),
                text=request.user_text.strip(),
                source_line=source_line,
            ))
        additions.extend(LineReadingTranscriptItem(
            kind="partner",
            character=turn.character,
            text=turn.text,
            source_line=turn.source_line,
        ) for turn in response.assistant_turns)
        if response.feedback:
            additions.append(LineReadingTranscriptItem(
                kind="feedback",
                text=response.feedback,
            ))

        engine_counts[response.engine] = engine_counts.get(response.engine, 0) + 1
        next_index = response.next_line_index
        updated_session = LineReadingSession(
            session_id=session_id,
            script_id=analysis.script_id,
            scene_id=scene.scene_id,
            scene_title=scene.title,
            character=request.character.strip(),
            mode=request.mode,
            line_index=next_index if next_index is not None else len(scene.lines),
            actor_prompt=response.actor_prompt,
            transcript=[*previous_transcript, *additions],
            turn_count=previous_turn_count + 1,
            engine_counts=engine_counts,
            finished=response.finished,
            created_at=created_at,
            updated_at=now,
        )
        return response.model_copy(update={
            "session_id": session_id,
            "transcript": updated_session.transcript,
            "turn_count": updated_session.turn_count,
        }), updated_session
