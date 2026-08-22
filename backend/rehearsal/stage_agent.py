"""舞台可视化 Agent：把场景证据转换为角色、道具和事件序列。"""

from __future__ import annotations

import re

from backend.rehearsal.models import (
    Scene,
    StageActor,
    StageEvent,
    StagePosition,
    StageProp,
    StageVisualization,
    ScriptAnalysis,
)


_POSITIONS: tuple[StagePosition, ...] = (
    "center_left",
    "center",
    "center_right",
    "upstage_left",
    "upstage_right",
    "downstage_left",
    "downstage_center",
    "downstage_right",
)


def _position_from_text(text: str, fallback: StagePosition) -> StagePosition:
    if re.search(r"舞台后|后方|后侧|上场口", text):
        if "左" in text:
            return "upstage_left"
        if "右" in text:
            return "upstage_right"
        return "upstage_center"
    if re.search(r"台口|舞台前|前方|前侧", text):
        if "左" in text:
            return "downstage_left"
        if "右" in text:
            return "downstage_right"
        return "downstage_center"
    if "左" in text:
        return "center_left"
    if "右" in text:
        return "center_right"
    if re.search(r"中央|中心|中间", text):
        return "center"
    return fallback


def _matching_names(text: str, names: list[str]) -> list[str]:
    return [name for name in sorted(names, key=len, reverse=True) if name and name in text]


class StageVisualizationAgent:
    """Generate a deterministic, source-backed stage map for one scene."""

    def render(self, analysis: ScriptAnalysis, scene_id: str) -> StageVisualization:
        scene = next((item for item in analysis.scenes if item.scene_id == scene_id), None)
        if scene is None:
            raise ValueError("舞台可视化场次不存在")

        actors = self._initial_actors(scene)
        props = self._initial_props(scene)
        raw_events: list[tuple[int, int, str, str, str]] = []
        warnings: list[str] = []

        if not scene.stage_directions:
            warnings.append("本场没有识别到括号舞台提示，角色位置使用默认布局；建议人工补充走位。")

        for direction in scene.stage_directions:
            subject_names = _matching_names(direction.text, list(actors))
            if "所有人" in direction.text or "大家" in direction.text:
                subject_names = list(actors)
            if not subject_names and direction.kind in {"entrance", "exit", "movement"}:
                warnings.append(f"第 {direction.source_line} 行舞台提示未匹配到具体角色：{direction.text}")

            position = _position_from_text(direction.text, "unknown")
            if direction.kind == "entrance":
                for name in subject_names:
                    actors[name].status = "onstage"
                    if position != "unknown":
                        actors[name].position = position
            elif direction.kind == "exit":
                for name in subject_names:
                    actors[name].status = "offstage"
            elif direction.kind == "movement":
                for name in subject_names:
                    if position != "unknown":
                        actors[name].position = position

            event_subject = "、".join(subject_names) or "舞台"
            raw_events.append((direction.source_line, 0, direction.kind, event_subject, direction.text))

            for prop_name in _matching_names(direction.text, list(props)):
                props[prop_name].source_lines.append(direction.source_line)
                if position != "unknown":
                    props[prop_name].position = position
                if direction.kind != "prop":
                    raw_events.append((direction.source_line, 1, "prop", prop_name, direction.text))

        for line in scene.lines:
            if line.character in actors:
                actors[line.character].status = "onstage" if actors[line.character].status != "offstage" else "offstage"
                actors[line.character].source_lines.append(line.source.start_line)
            for prop_name in _matching_names(line.text, list(props)):
                props[prop_name].source_lines.append(line.source.start_line)
            raw_events.append((line.source.start_line, 2, "dialogue", line.character, line.text))

        events = [
            StageEvent(
                order=index,
                event_type=event_type,
                subject=subject,
                text=text,
                source_line=source_line,
            )
            for index, (source_line, _, event_type, subject, text) in enumerate(
                sorted(raw_events, key=lambda item: (item[0], item[1])),
                start=1,
            )
        ]
        actor_values = list(actors.values())
        prop_values = list(props.values())
        onstage = [actor.name for actor in actor_values if actor.status == "onstage"]
        summary = (
            f"第 {scene.number} 场当前识别 {len(onstage)} 名演员在台、"
            f"{len(prop_values)} 件道具和 {len(events)} 个舞台事件。"
        )
        return StageVisualization(
            script_id=analysis.script_id,
            scene_id=scene.scene_id,
            scene_number=scene.number,
            scene_title=scene.title,
            actors=actor_values,
            props=prop_values,
            events=events,
            summary=summary,
            warnings=warnings,
        )

    @staticmethod
    def _initial_actors(scene: Scene) -> dict[str, StageActor]:
        names: list[str] = []
        for name in [*scene.characters, *(line.character for line in scene.lines)]:
            clean = name.strip()
            if clean and clean not in names:
                names.append(clean)
        return {
            name: StageActor(
                name=name,
                status="onstage" if any(line.character == name for line in scene.lines) else "unknown",
                position=_POSITIONS[index % len(_POSITIONS)],
            )
            for index, name in enumerate(names)
        }

    @staticmethod
    def _initial_props(scene: Scene) -> dict[str, StageProp]:
        return {
            name: StageProp(name=name, position=_POSITIONS[index % len(_POSITIONS)])
            for index, name in enumerate(scene.props)
            if name.strip()
        }
