"""剧本 RAG Agent：先检索带行号的原文证据，再生成可核对的回答。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from backend.config import embedding_mode_of
from backend.llm_provider import (
    HumanMessage,
    ProviderNotConfigured,
    SystemMessage,
    get_embedding,
    get_llm,
    resolve_embedding_config,
)
from backend.rehearsal.models import (
    ScriptAnalysis,
    ScriptRagEvidence,
    ScriptRagQueryRequest,
    ScriptRagResponse,
)
from backend.vector_memory import _cosine_similarity


logger = logging.getLogger("uvicorn")

_CJK_NUMBER = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")
_QUESTION_MARKERS = {
    "角色": ("dialogue", "scene_context"),
    "演员": ("dialogue", "scene_context"),
    "台词": ("dialogue",),
    "说": ("dialogue",),
    "道具": ("stage_direction", "scene_context"),
    "拿": ("stage_direction", "dialogue"),
    "放": ("stage_direction", "dialogue"),
    "走位": ("stage_direction",),
}

_RAG_SYSTEM_PROMPT = """你是奇点剧团的剧本问答 Agent。
只根据提供的剧本证据回答问题，不得补写证据中没有的剧情、人物关系、时间地点或动机。
回答必须引用至少一个证据 ID，格式为 [证据ID]；如果证据不足，要明确说无法从当前剧本确认。
只输出一个 JSON 对象，不要输出 Markdown，格式为：
{"answer":"回答，包含 [证据ID]","note":"一句话说明回答依据"}
"""


class _RagDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=4_000)
    note: str = Field(default="", max_length=500)


@dataclass(frozen=True)
class _RagDocument:
    evidence_id: str
    scene_id: str
    scene_number: int
    scene_title: str
    source_type: str
    character: str
    text: str
    source_line: int
    search_text: str


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


def _compact(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", value).casefold()


def _terms(value: str) -> set[str]:
    compact = _compact(value)
    terms: set[str] = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", compact))
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", compact):
        terms.update(run[index:index + 2] for index in range(len(run) - 1))
    return {term for term in terms if term}


def _scene_number_alias(number: int) -> str:
    if 0 <= number < len(_CJK_NUMBER):
        return _CJK_NUMBER[number]
    return str(number)


def _scene_label(number: int, title: str) -> str:
    return f"第{number}场 第{_scene_number_alias(number)}场 {title}"


def _build_documents(analysis: ScriptAnalysis) -> list[_RagDocument]:
    documents: list[_RagDocument] = []
    for scene in analysis.scenes:
        label = _scene_label(scene.number, scene.title)
        context = (
            f"{label}；角色：{'、'.join(scene.characters)}；"
            f"道具：{'、'.join(scene.props) or '未识别'}"
        )
        documents.append(_RagDocument(
            evidence_id=f"{scene.scene_id}-context",
            scene_id=scene.scene_id,
            scene_number=scene.number,
            scene_title=scene.title,
            source_type="scene_context",
            character="",
            text=context,
            source_line=scene.source.start_line,
            search_text=f"{label} {context}",
        ))
        for direction_index, direction in enumerate(scene.stage_directions, start=1):
            documents.append(_RagDocument(
                evidence_id=f"{scene.scene_id}-stage-{direction_index}",
                scene_id=scene.scene_id,
                scene_number=scene.number,
                scene_title=scene.title,
                source_type="stage_direction",
                character="",
                text=direction.text,
                source_line=direction.source_line,
                search_text=f"{label} {direction.text}",
            ))
        for line in scene.lines:
            documents.append(_RagDocument(
                evidence_id=line.line_id,
                scene_id=scene.scene_id,
                scene_number=scene.number,
                scene_title=scene.title,
                source_type="dialogue",
                character=line.character,
                text=line.text,
                source_line=line.source.start_line,
                search_text=f"{label} {line.character} {line.text}",
            ))
    return documents


def _rule_score(question: str, document: _RagDocument) -> tuple[float, str]:
    query = _compact(question)
    content = _compact(document.search_text)
    query_terms = _terms(question)
    content_terms = _terms(document.search_text)
    overlap = query_terms & content_terms
    score = min(0.45, len(overlap) * 0.09)
    reasons: list[str] = []

    if query and query in content:
        score += 0.42
        reasons.append("包含问题短语")
    if document.character and _compact(document.character) in query:
        score += 0.2
        reasons.append("匹配角色")
    scene_alias = f"第{_scene_number_alias(document.scene_number)}场"
    if scene_alias in question or f"第{document.scene_number}场" in question:
        score += 0.16
        reasons.append("匹配场次")
    for marker, preferred_types in _QUESTION_MARKERS.items():
        if marker in question and document.source_type in preferred_types:
            score += 0.08
            reasons.append(f"问题意图偏向{marker}")
            break
    if overlap:
        reasons.append(f"关键词重合 {len(overlap)} 个")
    return min(score, 0.99), "；".join(dict.fromkeys(reasons)) or "场次上下文匹配"


def _evidence_from_document(document: _RagDocument, score: float, reason: str) -> ScriptRagEvidence:
    return ScriptRagEvidence(
        evidence_id=document.evidence_id,
        scene_id=document.scene_id,
        scene_number=document.scene_number,
        scene_title=document.scene_title,
        source_type=document.source_type,  # type: ignore[arg-type]
        character=document.character,
        text=document.text,
        source_line=document.source_line,
        score=round(max(0.0, min(1.0, score)), 4),
        match_reason=reason,
    )


def _rules_answer(title: str, evidence: list[ScriptRagEvidence]) -> str:
    if not evidence:
        return "当前剧本中没有检索到与问题直接匹配的原文证据。请换一个角色、场次、道具或台词关键词。"
    lines = [f"根据《{title}》的原文检索，找到 {len(evidence)} 条相关证据："]
    for item in evidence[:5]:
        speaker = f"{item.character}：" if item.character else "舞台提示："
        lines.append(
            f"- [{item.evidence_id}] 第{item.scene_number}场·{item.scene_title}·原文第{item.source_line}行，"
            f"{speaker}{item.text}"
        )
    return "\n".join(lines)


class ScriptRagAgent:
    """Retrieve script evidence first, then optionally ask an LLM to synthesize it."""

    def answer(
        self,
        analysis: ScriptAnalysis,
        request: ScriptRagQueryRequest,
        *,
        user_id: str | None = None,
    ) -> ScriptRagResponse:
        documents = _build_documents(analysis)
        retrieval_engine = "rules"
        scored: list[tuple[_RagDocument, float, str]]
        if request.retrieval_mode == "semantic":
            try:
                scored = self._semantic_search(documents, request.question, request.top_k, user_id)
                retrieval_engine = "semantic"
            except Exception as exc:  # noqa: BLE001 - semantic retrieval is optional
                logger.warning("Script RAG semantic fallback: %s", exc)
                scored = self._rule_search(documents, request.question, request.top_k)
                retrieval_engine = "rules-fallback"
        else:
            scored = self._rule_search(documents, request.question, request.top_k)

        evidence = [_evidence_from_document(doc, score, reason) for doc, score, reason in scored]
        answer = _rules_answer(analysis.title, evidence)
        engine = "rules"
        note = (
            "本地规则根据角色、场次、道具和台词关键词检索；每条回答都保留原文行号。"
            if evidence else
            "没有命中足够证据，未让模型猜测剧本内容。"
        )

        if evidence and request.answer_mode in {"auto", "llm"}:
            try:
                draft = self._answer_with_llm(
                    request.question,
                    evidence,
                    user_id=user_id,
                )
                answer = draft.answer.strip()
                engine = "llm"
                note = draft.note.strip() or "LLM 只基于检索到的剧本证据组织回答。"
            except Exception as exc:  # noqa: BLE001 - LLM is an optional branch
                logger.warning("Script RAG LLM fallback: %s", exc)
                engine = "fallback"
                note = "当前未使用 LLM，已回退到带原文证据的规则回答。"

        return ScriptRagResponse(
            script_id=analysis.script_id,
            script_title=analysis.title,
            question=request.question,
            answer=answer,
            evidence=evidence,
            engine=engine,
            retrieval_engine=retrieval_engine,  # type: ignore[arg-type]
            note=note,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _rule_search(
        documents: list[_RagDocument],
        question: str,
        top_k: int,
    ) -> list[tuple[_RagDocument, float, str]]:
        scored = [
            (document, *_rule_score(question, document))
            for document in documents
        ]
        scored = [item for item in scored if item[1] > 0]
        scored.sort(key=lambda item: (-item[1], item[0].source_line, item[0].evidence_id))
        return scored[:top_k]

    @staticmethod
    def _semantic_search(
        documents: list[_RagDocument],
        question: str,
        top_k: int,
        user_id: str | None,
    ) -> list[tuple[_RagDocument, float, str]]:
        if not user_id:
            raise ProviderNotConfigured("Embedding")
        config = resolve_embedding_config(user_id)
        mode = embedding_mode_of(config["backend"], config["api_base"], config["api_key"])
        configured = bool(config["api_key"]) if mode == "api" else bool(config["local_model"] or config["local_path"])
        if not configured:
            raise ProviderNotConfigured("Embedding")
        model = get_embedding(user_id)
        query_vector = np.asarray(model.get_text_embedding(question), dtype=np.float32)
        matrix = np.asarray(
            model.get_text_embedding_batch([document.search_text for document in documents]),
            dtype=np.float32,
        )
        similarities = _cosine_similarity(query_vector, matrix)
        scored = [
            (document, max(0.0, min(1.0, float(similarities[index]))), "语义向量相似度")
            for index, document in enumerate(documents)
        ]
        scored.sort(key=lambda item: (-item[1], item[0].source_line, item[0].evidence_id))
        return [item for item in scored[:top_k] if item[1] > 0]

    @staticmethod
    def _answer_with_llm(
        question: str,
        evidence: list[ScriptRagEvidence],
        *,
        user_id: str | None,
    ) -> _RagDraft:
        context = [
            {
                "证据ID": item.evidence_id,
                "场次": f"第{item.scene_number}场·{item.scene_title}",
                "原文行号": item.source_line,
                "角色": item.character,
                "原文": item.text,
            }
            for item in evidence
        ]
        llm = get_llm(user_id)
        response = llm.invoke([
            SystemMessage(_RAG_SYSTEM_PROMPT),
            HumanMessage(json.dumps({"问题": question, "证据": context}, ensure_ascii=False)),
        ])
        draft = _RagDraft.model_validate(_load_json(response))
        if not any(item.evidence_id in draft.answer for item in evidence):
            raise ValueError("LLM answer omitted script evidence citation")
        if llm.last_attempts > 1:
            draft.note = f"{draft.note} LLM 请求在第 {llm.last_attempts} 次尝试后成功。".strip()[:500]
        return draft
