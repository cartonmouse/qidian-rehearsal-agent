"""剧本解读 Agent 的最小可运行编排。

编排显式暴露每一步的输入输出：摄取、分场、并行实体抽取、校验、修复、汇总。
当前实体抽取节点是可解释的本地工具，下一步可以在同一个状态契约中增加 LLM
结构化抽取和人工确认节点。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from backend.rehearsal.models import AgentStep, Character, Prop, ScriptAnalysis
from backend.rehearsal.parser import extract_props, extract_scene, normalize_lines, split_scene_blocks


class ScriptAnalysisAgent:
    """把剧本文本转换为可供排练模块继续消费的结构化产出。"""

    def run(
        self,
        *,
        title: str,
        version_label: str,
        script_text: str,
        script_id: str | None = None,
    ) -> ScriptAnalysis:
        trace: list[AgentStep] = []

        lines = normalize_lines(script_text)
        trace.append(AgentStep(
            name="ingest",
            status="completed",
            summary="规范化换行并保留原始行号，供结果回指剧本原文。",
            output_count=len(lines),
        ))

        blocks, split_warnings = split_scene_blocks(lines)
        trace.append(AgentStep(
            name="split_scenes",
            status="completed",
            summary=f"识别出 {len(blocks)} 个场次边界。",
            output_count=len(blocks),
        ))

        # 每个场次彼此独立，使用线程池模拟并行任务节点；未来可替换为异步 LLM 调用。
        worker_count = min(4, max(1, len(blocks)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            extracted = list(executor.map(extract_scene, blocks))
        scenes = [scene for scene, _ in extracted]
        extraction_warnings = [warning for _, warnings in extracted for warning in warnings]
        trace.append(AgentStep(
            name="extract_entities_parallel",
            status="completed",
            summary=f"并行提取 {len(scenes)} 个场次的角色、台词和道具。",
            output_count=sum(len(scene.lines) for scene in scenes),
        ))

        warnings = [*split_warnings, *extraction_warnings]
        if not scenes:
            warnings.append("没有可用场次，无法生成排练结构。")
        if not any(scene.lines for scene in scenes):
            warnings.append("全文没有识别到角色台词，建议人工确认剧本格式。")
        trace.append(AgentStep(
            name="validate",
            status="completed",
            summary=f"校验完成，发现 {len(warnings)} 条需要关注的信息。",
            output_count=len(warnings),
        ))

        # 修复策略保持保守：不凭空生成角色，只把缺失分场的文本归到默认场次并留下警告。
        repaired = bool(split_warnings)
        trace.append(AgentStep(
            name="repair",
            status="repaired" if repaired else "completed",
            summary="已应用保守修复并保留人工复核提示。" if repaired else "无需自动修复。",
            output_count=len(warnings),
        ))

        characters_by_name: dict[str, Character] = {}
        props_by_name: dict[str, Prop] = {}
        for scene in scenes:
            for line in scene.lines:
                character = characters_by_name.setdefault(line.character, Character(name=line.character))
                if scene.scene_id not in character.scene_ids:
                    character.scene_ids.append(scene.scene_id)
                character.dialogue_count += 1
            for prop in scene.props:
                item = props_by_name.setdefault(prop, Prop(name=prop))
                if scene.scene_id not in item.scene_ids:
                    item.scene_ids.append(scene.scene_id)
                item.mention_count += 1

        analysis = ScriptAnalysis(
            script_id=script_id or uuid4().hex,
            title=title,
            version_label=version_label,
            scenes=scenes,
            characters=list(characters_by_name.values()),
            props=list(props_by_name.values()),
            warnings=warnings,
            trace=trace,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return analysis
