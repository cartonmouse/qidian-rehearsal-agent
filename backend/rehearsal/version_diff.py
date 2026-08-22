"""剧本版本差异 Agent：用原始场次和台词证据解释版本变化。"""

from __future__ import annotations

import difflib
import re

from backend.rehearsal.models import (
    DialogueLine,
    ResourceAuditRecord,
    Scene,
    SceneDiff,
    ScriptLineChange,
    ScriptAnalysis,
    ScriptVersionDiff,
    VersionResourceAuditMatch,
    VersionDownstreamImpact,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


def _scene_characters(scene: Scene) -> set[str]:
    return {item.strip() for item in [*scene.characters, *(line.character for line in scene.lines)] if item.strip()}


def _scene_props(scene: Scene) -> set[str]:
    return {item.strip() for item in scene.props if item.strip()}


def _line_key(line: DialogueLine) -> tuple[str, str]:
    return line.character.strip(), _normalize(line.text)


def _line_change(
    change_type: str,
    old_line: DialogueLine | None,
    new_line: DialogueLine | None,
) -> ScriptLineChange:
    return ScriptLineChange(
        change_type=change_type,
        character=(new_line or old_line).character,
        old_text=old_line.text if old_line else "",
        new_text=new_line.text if new_line else "",
        old_source_line=old_line.source.start_line if old_line else None,
        new_source_line=new_line.source.start_line if new_line else None,
    )


def _compare_lines(old_lines: list[DialogueLine], new_lines: list[DialogueLine]) -> list[ScriptLineChange]:
    matcher = difflib.SequenceMatcher(
        a=[_line_key(line) for line in old_lines],
        b=[_line_key(line) for line in new_lines],
        autojunk=False,
    )
    changes: list[ScriptLineChange] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        old_chunk = old_lines[old_start:old_end]
        new_chunk = new_lines[new_start:new_end]
        if tag == "replace":
            paired = min(len(old_chunk), len(new_chunk))
            changes.extend(
                _line_change("modified", old_chunk[index], new_chunk[index])
                for index in range(paired)
            )
            changes.extend(_line_change("removed", line, None) for line in old_chunk[paired:])
            changes.extend(_line_change("added", None, line) for line in new_chunk[paired:])
        elif tag == "delete":
            changes.extend(_line_change("removed", line, None) for line in old_chunk)
        elif tag == "insert":
            changes.extend(_line_change("added", None, line) for line in new_chunk)
    return changes


class ScriptVersionDiffAgent:
    """Compare two saved analyses without allowing an LLM to invent changes."""

    def compare(self, previous: ScriptAnalysis, current: ScriptAnalysis) -> ScriptVersionDiff:
        old_by_number = {scene.number: scene for scene in previous.scenes}
        new_by_number = {scene.number: scene for scene in current.scenes}
        scene_diffs: list[SceneDiff] = []

        for number in sorted(set(old_by_number) | set(new_by_number)):
            old_scene = old_by_number.get(number)
            new_scene = new_by_number.get(number)
            scene_diffs.append(self._compare_scene(number, old_scene, new_scene))

        added_count = sum(item.status == "added" for item in scene_diffs)
        removed_count = sum(item.status == "removed" for item in scene_diffs)
        changed_count = sum(item.status == "changed" for item in scene_diffs)
        unchanged_count = sum(item.status == "unchanged" for item in scene_diffs)
        total_changes = added_count + removed_count + changed_count
        if total_changes == 0:
            summary = "两个剧本版本的场次、角色、道具和台词没有检测到变化。"
        else:
            summary = (
                f"共检测到 {total_changes} 个受影响场次：新增 {added_count} 场、"
                f"删除 {removed_count} 场、修改 {changed_count} 场。"
            )
        downstream_impacts = self._downstream_impacts(scene_diffs)
        impact_types = {item.impact_type for item in downstream_impacts}

        return ScriptVersionDiff(
            previous_script_id=previous.script_id,
            current_script_id=current.script_id,
            previous_version_label=previous.version_label,
            current_version_label=current.version_label,
            previous_title=previous.title,
            current_title=current.title,
            added_scene_count=added_count,
            removed_scene_count=removed_count,
            changed_scene_count=changed_count,
            unchanged_scene_count=unchanged_count,
            scenes=scene_diffs,
            summary=summary,
            downstream_impacts=downstream_impacts,
            requires_schedule_review="schedule" in impact_types,
            requires_line_reading_review="line-reading" in impact_types,
            requires_resource_review="resource" in impact_types,
        )

    def _compare_scene(
        self,
        number: int,
        old_scene: Scene | None,
        new_scene: Scene | None,
    ) -> SceneDiff:
        if old_scene is None and new_scene is not None:
            characters = sorted(_scene_characters(new_scene))
            props = sorted(_scene_props(new_scene))
            return SceneDiff(
                scene_key=f"scene-{number}",
                scene_number=number,
                status="added",
                new_scene_id=new_scene.scene_id,
                new_title=new_scene.title,
                added_characters=characters,
                added_props=props,
                line_changes=[_line_change("added", None, line) for line in new_scene.lines],
                impact=self._impact(
                    characters,
                    [],
                    props,
                    [],
                    [line.character for line in new_scene.lines],
                ),
                summary=f"新增第 {number} 场：{new_scene.title}。",
            )
        if old_scene is not None and new_scene is None:
            characters = sorted(_scene_characters(old_scene))
            props = sorted(_scene_props(old_scene))
            return SceneDiff(
                scene_key=f"scene-{number}",
                scene_number=number,
                status="removed",
                old_scene_id=old_scene.scene_id,
                old_title=old_scene.title,
                removed_characters=characters,
                removed_props=props,
                line_changes=[_line_change("removed", line, None) for line in old_scene.lines],
                impact=self._impact(
                    [],
                    characters,
                    [],
                    props,
                    [line.character for line in old_scene.lines],
                ),
                summary=f"删除第 {number} 场：{old_scene.title}。",
            )

        assert old_scene is not None and new_scene is not None
        old_characters = _scene_characters(old_scene)
        new_characters = _scene_characters(new_scene)
        old_props = _scene_props(old_scene)
        new_props = _scene_props(new_scene)
        line_changes = _compare_lines(old_scene.lines, new_scene.lines)
        added_characters = sorted(new_characters - old_characters)
        removed_characters = sorted(old_characters - new_characters)
        added_props = sorted(new_props - old_props)
        removed_props = sorted(old_props - new_props)
        title_changed = _normalize(old_scene.title) != _normalize(new_scene.title)
        changed = bool(title_changed or added_characters or removed_characters or added_props or removed_props or line_changes)

        if not changed:
            summary = f"第 {number} 场没有变化。"
        else:
            pieces = []
            if title_changed:
                pieces.append("场次标题变化")
            if line_changes:
                pieces.append(f"台词变化 {len(line_changes)} 处")
            if added_characters or removed_characters:
                pieces.append("角色清单变化")
            if added_props or removed_props:
                pieces.append("道具清单变化")
            summary = f"第 {number} 场变更：" + "、".join(pieces) + "。"

        return SceneDiff(
            scene_key=f"scene-{number}",
            scene_number=number,
            status="changed" if changed else "unchanged",
            old_scene_id=old_scene.scene_id,
            new_scene_id=new_scene.scene_id,
            old_title=old_scene.title,
            new_title=new_scene.title,
            added_characters=added_characters,
            removed_characters=removed_characters,
            added_props=added_props,
            removed_props=removed_props,
            line_changes=line_changes,
            impact=self._impact(
                added_characters,
                removed_characters,
                added_props,
                removed_props,
                [change.character for change in line_changes],
            ),
            summary=summary,
        )

    @staticmethod
    def _impact(
        added_characters: list[str],
        removed_characters: list[str],
        added_props: list[str],
        removed_props: list[str],
        line_characters: list[str],
    ) -> list[str]:
        impact: list[str] = []
        if added_characters:
            impact.append("新增演员：" + "、".join(added_characters))
        if removed_characters:
            impact.append("减少演员：" + "、".join(removed_characters))
        if added_props:
            impact.append("新增道具：" + "、".join(added_props))
        if removed_props:
            impact.append("移除道具：" + "、".join(removed_props))
        unique_line_characters = sorted(set(line_characters))
        if unique_line_characters:
            impact.append("需重新核对台词：" + "、".join(unique_line_characters))
        return impact

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return sorted({value.strip() for value in values if value.strip()})

    @classmethod
    def _downstream_impacts(cls, scene_diffs: list[SceneDiff]) -> list[VersionDownstreamImpact]:
        """Translate scene facts into explicit, deterministic downstream actions."""

        impacts: list[VersionDownstreamImpact] = []
        for scene in scene_diffs:
            if scene.status == "unchanged":
                continue

            scene_title = scene.new_title or scene.old_title or f"第 {scene.scene_number} 场"
            line_characters = [change.character for change in scene.line_changes]
            affected_characters = cls._unique(
                [*scene.added_characters, *scene.removed_characters, *line_characters]
            )
            affected_props = cls._unique([*scene.added_props, *scene.removed_props])
            roster_changed = bool(scene.added_characters or scene.removed_characters)
            schedule_severity = "high" if scene.status in {"added", "removed"} or roster_changed else "medium"
            if scene.status == "added":
                schedule_reason = f"第 {scene.scene_number} 场为新增场次，原有排练计划没有对应任务。"
                schedule_action = "人工确认新场次后重新生成调度，并检查已有排班。"
            elif scene.status == "removed":
                schedule_reason = f"第 {scene.scene_number} 场已从当前版本删除，原有排练任务可能仍然占用演员和场地。"
                schedule_action = "人工确认删除后重新生成调度，并清理不再需要的排班。"
            else:
                schedule_reason = f"{scene.summary} 原有调度中的演员、道具或时长可能已经失效。"
                schedule_action = "人工确认变更后重新生成调度，再检查演员档期与并行组。"
            impacts.append(
                VersionDownstreamImpact(
                    impact_type="schedule",
                    severity=schedule_severity,
                    scene_key=scene.scene_key,
                    scene_number=scene.scene_number,
                    scene_title=scene_title,
                    affected_characters=affected_characters,
                    affected_props=affected_props,
                    reason=schedule_reason,
                    action=schedule_action,
                )
            )

            if scene.line_changes:
                impacts.append(
                    VersionDownstreamImpact(
                        impact_type="line-reading",
                        severity="high",
                        scene_key=scene.scene_key,
                        scene_number=scene.scene_number,
                        scene_title=scene_title,
                        affected_characters=cls._unique(line_characters),
                        reason=(
                            f"第 {scene.scene_number} 场有 {len(scene.line_changes)} 处台词变化，"
                            "旧对词进度和回应可能不再对应当前台词。"
                        ),
                        action="切换到当前版本重新开始对词，避免沿用旧台词进度。",
                    )
                )

            if affected_props:
                impacts.append(
                    VersionDownstreamImpact(
                        impact_type="resource",
                        severity="medium",
                        scene_key=scene.scene_key,
                        scene_number=scene.scene_number,
                        scene_title=scene_title,
                        affected_characters=[],
                        affected_props=affected_props,
                        reason=(
                            f"第 {scene.scene_number} 场的道具清单发生变化：{'、'.join(affected_props)}。"
                            "现有库存结论需要重新确认。"
                        ),
                        action="重新执行排练前道具检查，确认库存与维修状态。",
                    )
                )
        return impacts


def attach_resource_audit_matches(
    diff: ScriptVersionDiff,
    audits: list[ResourceAuditRecord],
) -> ScriptVersionDiff:
    """Attach user-scoped resource evidence to resource downstream impacts."""
    if not audits:
        return diff

    enriched: list[VersionDownstreamImpact] = []
    for impact in diff.downstream_impacts:
        if impact.impact_type != "resource" or not impact.affected_props:
            enriched.append(impact)
            continue

        matches: list[VersionResourceAuditMatch] = []
        seen: set[tuple[str, str]] = set()
        for audit in audits:
            for change in audit.changes:
                label = _normalize(change.label)
                related = any(
                    prop_key == label
                    or (len(prop_key) >= 2 and prop_key in label)
                    or (len(label) >= 2 and label in prop_key)
                    for prop_key in (_normalize(prop) for prop in impact.affected_props)
                    if prop_key and label
                )
                if not related or (audit.audit_id, change.resource_id) in seen:
                    continue
                seen.add((audit.audit_id, change.resource_id))
                matches.append(VersionResourceAuditMatch(
                    audit_id=audit.audit_id,
                    resource_type=audit.resource_type,
                    change_type=change.change_type,
                    resource_id=change.resource_id,
                    label=change.label,
                    summary=change.summary,
                    created_at=audit.created_at,
                ))
                if len(matches) >= 8:
                    break
            if len(matches) >= 8:
                break
        enriched.append(impact.model_copy(update={"resource_audit_matches": matches}))

    return diff.model_copy(update={"downstream_impacts": enriched})
