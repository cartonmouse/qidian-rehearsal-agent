"""宣传文案 Agent：结构化生成剧团宣传文案，并在无模型时安全降级。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from backend.llm_provider import HumanMessage, SystemMessage, get_llm
from backend.rehearsal.models import PromoCopyRequest, PromoCopyResponse


logger = logging.getLogger("uvicorn")

_PROMO_SYSTEM_PROMPT = """你是奇点剧团的宣传文案 Agent。
根据给定的剧本结构和宣传 brief 生成中文宣传文案，只输出一个 JSON 对象，不要 Markdown：
{"headline":"标题","short_copy":"短文案","long_copy":"长文案","hashtags":["#标签"],"note":"说明"}

规则：
1. 只能使用输入中出现的剧名、场次标题、角色名和 brief，不得虚构剧情、演出时间、地点、演员履历或奖项。
2. headline 不超过 40 字，short_copy 不超过 120 字，long_copy 不超过 500 字，hashtags 最多 8 个。
3. 语气服从 tone；如果结构信息不足，要使用开放而诚实的表达，不要编造故事。
4. hashtags 每项必须以 # 开头，note 简述文案依据。
"""


class _PromoDraft(BaseModel):
    headline: str = Field(min_length=1, max_length=200)
    short_copy: str = Field(min_length=1, max_length=500)
    long_copy: str = Field(min_length=1, max_length=1_500)
    hashtags: list[str] = Field(default_factory=list, max_length=8)
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


def _safe_tag(value: str) -> str:
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", "", value, flags=re.UNICODE)
    return f"#{clean}" if clean else ""


def _rules_draft(
    request: PromoCopyRequest,
    *,
    scene_titles: list[str],
    characters: list[str],
) -> _PromoDraft:
    title = request.work_title
    scene_hint = "、".join(scene_titles[:3]) if scene_titles else "排练现场"
    character_hint = "、".join(characters[:4]) if characters else "剧团成员"
    brief = request.brief or "把排练中的观察、关系和舞台行动分享给观众。"
    audience_suffix = {
        "audience": "邀请观众走近这次舞台相遇。",
        "recruitment": "欢迎愿意一起排练、观察和创作的新伙伴。",
        "media": "适合作为剧团动态和创作记录的介绍。",
        "festival": "让一次排练中的现场感走向更大的舞台。",
    }[request.audience]
    headline = f"奇点剧团《{title}》｜让排练成为一次相遇"
    short_copy = f"{title} 从{scene_hint}出发，记录{character_hint}在舞台上的靠近与选择。{audience_suffix}"
    long_copy = (
        f"奇点剧团正在排练《{title}》。这一次，我们从{scene_hint}出发，"
        f"把{character_hint}的舞台行动交给时间、身体和彼此的回应。"
        f"宣传 brief：{brief} {audience_suffix}"
    )
    hashtags = [tag for tag in [_safe_tag("奇点剧团"), _safe_tag(title), _safe_tag("话剧排练")] if tag]
    return _PromoDraft(
        headline=headline,
        short_copy=short_copy,
        long_copy=long_copy,
        hashtags=hashtags,
        note="本地规则仅使用剧名、场次标题、角色和宣传 brief 生成；未配置 LLM 时仍可直接使用。",
    )


class PromoCopyAgent:
    """Generate publicity copy with a validated LLM branch and a deterministic fallback."""

    def generate(
        self,
        request: PromoCopyRequest,
        *,
        copy_id: str,
        script_title: str = "",
        scene_titles: list[str] | None = None,
        characters: list[str] | None = None,
        user_id: str | None = None,
    ) -> PromoCopyResponse:
        effective_title = script_title or request.work_title
        draft = _rules_draft(
            request.model_copy(update={"work_title": effective_title}),
            scene_titles=scene_titles or [],
            characters=characters or [],
        )
        engine = "rules" if request.analysis_mode == "rules" else "fallback"
        note = draft.note

        if request.analysis_mode in {"auto", "llm"}:
            try:
                draft = self._generate_with_llm(
                    request,
                    work_title=effective_title,
                    scene_titles=scene_titles or [],
                    characters=characters or [],
                    user_id=user_id,
                )
                engine = "llm"
                note = draft.note or "LLM 已根据剧本结构生成宣传文案。"
            except Exception as exc:  # noqa: BLE001 - graceful degradation is intentional
                logger.warning("Promo copy LLM fallback: %s", exc)
                note = "当前未使用 LLM，已使用本地规则生成；文案只引用已保存的剧本结构。"

        return PromoCopyResponse(
            copy_id=copy_id,
            script_id=request.script_id,
            work_title=effective_title,
            audience=request.audience,
            tone=request.tone,
            brief=request.brief,
            headline=draft.headline.strip(),
            short_copy=draft.short_copy.strip(),
            long_copy=draft.long_copy.strip(),
            hashtags=[tag if tag.startswith("#") else f"#{tag}" for tag in draft.hashtags],
            engine=engine,
            note=note,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_with_llm(
        self,
        request: PromoCopyRequest,
        *,
        work_title: str,
        scene_titles: list[str],
        characters: list[str],
        user_id: str | None,
    ) -> _PromoDraft:
        context = {
            "剧名": work_title,
            "场次标题": scene_titles,
            "角色名": characters,
            "受众": request.audience,
            "语气": request.tone,
            "宣传 brief": request.brief,
        }
        response = get_llm(user_id).invoke([
            SystemMessage(_PROMO_SYSTEM_PROMPT),
            HumanMessage(json.dumps(context, ensure_ascii=False)),
        ])
        return _PromoDraft.model_validate(_load_json(response))
