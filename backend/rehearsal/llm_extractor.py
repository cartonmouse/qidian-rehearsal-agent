"""Optional LLM scene extraction with strict JSON and source validation.

The local parser remains the safe fallback.  This module only handles the
semantic extraction branch; it never decides whether a scene exists or trusts
an unvalidated model response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.llm_provider import HumanMessage, SystemMessage, get_llm
from backend.rehearsal.models import DialogueLine, Scene, SourceSpan
from backend.rehearsal.parser import SceneBlock, parse_dialogue_line


logger = logging.getLogger("uvicorn")


class LLMDialogueDraft(BaseModel):
    """The only dialogue shape accepted from the model."""

    character: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class LLMSceneDraft(BaseModel):
    title: str = Field(default="", max_length=200)
    characters: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    costumes: list[str] = Field(default_factory=list)
    lines: list[LLMDialogueDraft] = Field(default_factory=list)


_SYSTEM_PROMPT = """你是话剧剧本结构化解析器。
只输出一个 JSON 对象，不要输出 Markdown、解释或代码块。对象格式必须是：
{
  "title": "本场标题",
  "characters": ["角色名"],
  "props": ["道具名"],
  "costumes": ["原文明确出现的服装或穿戴物"],
  "lines": [
    {"character": "角色名", "text": "台词原文", "start_line": 12, "end_line": 12}
  ]
}

要求：
1. 只提取当前场次，不要补写原文不存在的角色、道具、服装或台词。
2. 台词 text 必须尽量逐字复制输入中的原文；舞台提示不放入 lines。
3. start_line/end_line 必须使用输入前缀中的真实行号。
4. costumes 只记录原文明确写出的服装或穿戴物，不要根据角色身份、年代或场景猜测。
5. 无法确定的字段使用空数组或空字符串，不要猜测。
"""


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _source_dialogue_text(lines: list[str]) -> str:
    """Return dialogue text from source lines, stripping only speaker prefixes."""
    parts: list[str] = []
    for raw_line in lines:
        text = raw_line.strip()
        parsed = parse_dialogue_line(text)
        parts.append(parsed[1] if parsed else text)
    return "\n".join(parts).strip()


def _compact_text(value: str) -> str:
    return "".join(value.split())


def _load_json(text: str) -> dict[str, Any]:
    """Accept plain JSON and the fenced JSON some providers still return."""
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
    if isinstance(payload, dict) and isinstance(payload.get("scene"), dict):
        payload = payload["scene"]
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


def extract_scene_with_llm(block: SceneBlock, user_id: str) -> tuple[Scene, list[str]]:
    """Extract one scene and verify every returned line against source bounds."""
    numbered_source = "\n".join(f"{line_number}: {text}" for line_number, text in block.lines)
    llm = get_llm(user_id)
    response = llm.invoke([
        SystemMessage(_SYSTEM_PROMPT),
        HumanMessage(
            f"当前场次编号：{block.number}\n"
            f"当前场次标题：{block.title}\n"
            "以下是带原文行号的场次内容：\n"
            f"{numbered_source}"
        ),
    ])
    draft = LLMSceneDraft.model_validate(_load_json(response))

    source_by_line = {line_number: text for line_number, text in block.lines}
    warnings: list[str] = []
    if llm.last_attempts > 1:
        warnings.append(f"LLM 请求在第 {llm.last_attempts} 次尝试后成功，已保留本次重试记录。")
    lines: list[DialogueLine] = []
    for index, item in enumerate(draft.lines, start=1):
        if item.start_line > item.end_line:
            warnings.append(f"LLM 第 {index} 条台词行号范围无效，已忽略。")
            continue
        if item.start_line not in source_by_line or item.end_line not in source_by_line:
            warnings.append(f"LLM 第 {index} 条台词超出原文范围，已忽略。")
            continue
        source_excerpt = "\n".join(
            source_by_line[line_number]
            for line_number in range(item.start_line, item.end_line + 1)
            if line_number in source_by_line
        ).strip()
        source_dialogue = _source_dialogue_text(source_excerpt.splitlines())
        if _compact_text(item.text) != _compact_text(source_dialogue):
            warnings.append(f"LLM 第 {index} 条台词内容与原文不一致，已以原文为准。")
        lines.append(DialogueLine(
            line_id=f"scene-{block.number}-line-{len(lines) + 1}",
            character=item.character.strip(),
            # The model may locate a line but paraphrase it. The source remains
            # authoritative so downstream RAG, line reading and review never
            # turn an untrusted generation into a new script fact.
            text=source_dialogue,
            source=SourceSpan(
                start_line=item.start_line,
                end_line=item.end_line,
                excerpt=source_excerpt,
            ),
        ))

    if draft.lines and not lines:
        raise ValueError("LLM returned no source-valid dialogue lines")

    characters = _unique([*draft.characters, *(line.character for line in lines)])
    props = _unique(draft.props)
    source_text = "\n".join(text for _, text in block.lines)
    model_costumes = _unique(draft.costumes)
    costumes = [costume for costume in model_costumes if costume in source_text]
    if len(costumes) != len(model_costumes):
        warnings.append("LLM 返回了原文未明确出现的服装候选，已忽略并保留原文约束。")
    scene = Scene(
        scene_id=f"scene-{block.number}",
        number=block.number,
        title=draft.title.strip() or block.title,
        characters=characters,
        props=props,
        costumes=costumes,
        lines=lines,
        source=SourceSpan(
            start_line=block.start_line,
            end_line=block.end_line,
            excerpt="\n".join(text for _, text in block.lines[:3]).strip(),
        ),
    )
    if not lines:
        warnings.append(f"{block.title} 未识别到角色台词，请人工确认。")
    return scene, warnings
