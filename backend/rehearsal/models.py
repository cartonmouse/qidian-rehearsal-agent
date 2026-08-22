"""剧本解析 Agent 的领域模型与 API 模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class Scene(BaseModel):
    scene_id: str
    number: int = Field(ge=1)
    title: str
    characters: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    lines: list[DialogueLine] = Field(default_factory=list)
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


class ScriptParseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    version_label: str = Field(default="v1", min_length=1, max_length=50)
    script_text: str = Field(min_length=1, max_length=500_000)


class ScriptAnalysis(BaseModel):
    script_id: str
    title: str
    version_label: str
    analysis_mode: Literal["deterministic"] = "deterministic"
    parser_version: str = "0.1.0"
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
    created_at: str
