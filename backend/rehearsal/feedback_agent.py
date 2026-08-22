"""排练反馈镜像 Agent：把现场笔记整理成可追踪的下一步。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.llm_provider import HumanMessage, SystemMessage, get_llm
from backend.rehearsal.models import RehearsalFeedbackRequest, RehearsalFeedbackResponse


logger = logging.getLogger("uvicorn")

_POSITIVE_MARKERS = (
    "完成",
    "顺利",
    "清晰",
    "准确",
    "到位",
    "亮点",
    "很好",
    "成功",
    "保留",
    "有效",
    "稳定",
)
_BLOCKER_MARKERS = (
    "问题",
    "卡住",
    "忘词",
    "不清楚",
    "不足",
    "冲突",
    "缺少",
    "迟到",
    "道具",
    "待解决",
    "困难",
    "需要再",
)

_MIRROR_SYSTEM_PROMPT = """你是话剧团的排练复盘 Agent，也叫“镜子”。
你要把导演和演员的现场笔记整理成可执行的排练记录。
只输出一个 JSON 对象，不要输出 Markdown，格式为：
{"summary":"一句话总结","strengths":["已形成的有效产出"],"blockers":["仍阻塞排练的问题"],"next_actions":["下一次排练前可执行的动作"],"note":"一句简短提醒"}

规则：
1. 只依据输入笔记，不要虚构演员表现、时间或剧情事实。
2. strengths、blockers、next_actions 每项最多 6 条，优先保留具体、可核验的内容。
3. next_actions 必须是动作，而不是泛泛的“继续努力”。
4. 如果输入没有明确亮点或阻塞项，可以返回空数组。
"""


class _MirrorDraft(BaseModel):
    summary: str = Field(min_length=1, max_length=1_000)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    blockers: list[str] = Field(default_factory=list, max_length=6)
    next_actions: list[str] = Field(default_factory=list, max_length=6)
    note: str = Field(default="", max_length=500)


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


def _normalize_list(values: list[str], *, limit: int = 8) -> list[str]:
    result: list[str] = []
    for value in values:
        item = re.sub(r"^[\s\-*•\d.、)）]+", "", str(value)).strip()
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _note_fragments(notes: str) -> list[str]:
    fragments = [line.strip() for line in notes.splitlines() if line.strip()]
    if len(fragments) <= 1:
        fragments = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", notes) if part.strip()]
    return _normalize_list(fragments, limit=12)


def _rules_summary(request: RehearsalFeedbackRequest) -> _MirrorDraft:
    fragments = _note_fragments(request.notes)
    strengths = [item for item in fragments if any(marker in item for marker in _POSITIVE_MARKERS)]
    blockers = [item for item in fragments if any(marker in item for marker in _BLOCKER_MARKERS)]
    neutral = [item for item in fragments if item not in strengths and item not in blockers]
    outputs = _normalize_list(request.outputs, limit=6)

    if outputs:
        summary = f"本次排练记录了 {len(outputs)} 项具体产出。"
    elif fragments:
        summary = fragments[0]
    else:
        summary = "本次排练已完成现场记录，等待下一轮继续核对。"

    next_actions = []
    for item in blockers[:4]:
        next_actions.append(f"下次排练复核：{item}")
    if not next_actions and neutral:
        next_actions.append(f"下次排练开场回顾：{neutral[0]}")
    if not next_actions and outputs:
        next_actions.append(f"下次排练复用并验收：{outputs[0]}")

    return _MirrorDraft(
        summary=summary,
        strengths=_normalize_list(strengths, limit=6),
        blockers=_normalize_list(blockers, limit=6),
        next_actions=_normalize_list(next_actions, limit=6),
        note="本地规则根据反馈中的明确语句整理结果；可在下次排练后继续补充。",
    )


class RehearsalMirrorAgent:
    """Summarize raw rehearsal notes with an optional, validated LLM branch."""

    def summarize(
        self,
        request: RehearsalFeedbackRequest,
        *,
        record_id: str,
        script_title: str = "",
        scene_title: str = "",
        user_id: str | None = None,
    ) -> RehearsalFeedbackResponse:
        draft = _rules_summary(request)
        engine = "rules" if request.analysis_mode == "rules" else "fallback"
        note = draft.note

        if request.analysis_mode in {"auto", "llm"}:
            try:
                draft = self._summarize_with_llm(
                    request,
                    script_title=script_title,
                    scene_title=scene_title,
                    user_id=user_id,
                )
                engine = "llm"
                note = draft.note or "LLM 已根据原始反馈生成结构化复盘。"
            except Exception as exc:  # noqa: BLE001 - fallback is part of the Agent contract
                logger.warning("Rehearsal mirror LLM fallback: %s", exc)
                note = "当前未使用 LLM，已使用本地规则整理反馈；原始笔记仍完整保留。"

        return RehearsalFeedbackResponse(
            record_id=record_id,
            script_id=request.script_id,
            script_title=script_title,
            scene_id=request.scene_id,
            scene_title=scene_title,
            rehearsal_date=request.rehearsal_date,
            participants=_normalize_list(request.participants, limit=100),
            outputs=_normalize_list(request.outputs, limit=100),
            notes=request.notes,
            summary=draft.summary.strip(),
            strengths=_normalize_list(draft.strengths, limit=6),
            blockers=_normalize_list(draft.blockers, limit=6),
            next_actions=_normalize_list(draft.next_actions, limit=6),
            engine=engine,
            note=note,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _summarize_with_llm(
        self,
        request: RehearsalFeedbackRequest,
        *,
        script_title: str,
        scene_title: str,
        user_id: str | None,
    ) -> _MirrorDraft:
        context = {
            "剧本": script_title or "未关联剧本",
            "场次": scene_title or "未关联场次",
            "排练日期": request.rehearsal_date,
            "参与者": request.participants,
            "具体产出": request.outputs,
            "原始反馈": request.notes,
        }
        response = get_llm(user_id).invoke([
            SystemMessage(_MIRROR_SYSTEM_PROMPT),
            HumanMessage(json.dumps(context, ensure_ascii=False)),
        ])
        return _MirrorDraft.model_validate(_load_json(response))
