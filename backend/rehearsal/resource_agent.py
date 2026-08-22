"""资源检查 Agent：把剧本道具需求和人工维护的库存做可解释匹配。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from backend.rehearsal.models import (
    ResourceCheckResponse,
    ResourceInventoryItem,
    ResourceRequirement,
    RoomBooking,
    RoomBookingRequest,
    ScriptAnalysis,
)


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def room_booking_conflicts(candidate: RoomBookingRequest, existing: RoomBooking) -> bool:
    """Return whether two bookings occupy the same room and overlap in time."""
    return (
        candidate.room_name.casefold() == existing.room_name.casefold()
        and candidate.date == existing.date
        and candidate.start < existing.end
        and candidate.end > existing.start
    )


class ResourceAgent:
    """Deterministic resource readiness check with human-readable reasons.

    The first resource milestone intentionally keeps the inventory as the source
    of truth. The Agent only matches normalized names and never invents a prop
    that is absent from the parsed scene or inventory.
    """

    def check(
        self,
        analysis: ScriptAnalysis,
        inventory: list[ResourceInventoryItem],
        scene_id: str | None = None,
    ) -> ResourceCheckResponse:
        scenes = analysis.scenes
        if scene_id:
            scene = next((item for item in scenes if item.scene_id == scene_id), None)
            if scene is None:
                raise ValueError("关联场次不存在")
            scenes = [scene]
            scene_title = scene.title
        else:
            scene_title = "全剧本"

        requirements_by_name: dict[str, int] = {}
        display_names: dict[str, str] = {}
        for scene in scenes:
            scene_props = Counter(
                prop.strip()
                for prop in scene.props
                if prop and prop.strip()
            )
            for prop_name, count in scene_props.items():
                key = _normalize_name(prop_name)
                if not key:
                    continue
                display_names.setdefault(key, prop_name)
                if scene_id:
                    requirements_by_name[key] = requirements_by_name.get(key, 0) + count
                else:
                    # A script-level checklist asks whether each kind of prop
                    # exists at all; sequential scene mentions are not assumed
                    # to require simultaneous copies.
                    requirements_by_name[key] = 1

        inventory_by_name: dict[str, list[ResourceInventoryItem]] = defaultdict(list)
        for item in inventory:
            if item.category == "prop":
                inventory_by_name[_normalize_name(item.name)].append(item)

        requirements: list[ResourceRequirement] = []
        for key, required_quantity in requirements_by_name.items():
            items = inventory_by_name.get(key, [])
            available_quantity = sum(
                item.quantity for item in items if item.status == "available"
            )
            maintenance_quantity = sum(
                item.quantity for item in items if item.status == "maintenance"
            )
            name = display_names[key]
            if available_quantity >= required_quantity:
                status = "ready"
                note = f"可用 {available_quantity} 件"
            elif maintenance_quantity > 0:
                status = "maintenance"
                note = f"可用 {available_quantity} 件，另有 {maintenance_quantity} 件维修中"
            else:
                status = "missing"
                if items:
                    note = "库存记录存在，但当前没有可用数量"
                else:
                    note = "库存中没有匹配记录"
            requirements.append(ResourceRequirement(
                name=name,
                required_quantity=required_quantity,
                available_quantity=available_quantity,
                status=status,
                note=note,
            ))

        warnings: list[str] = []
        if not requirements:
            warnings.append("当前检查范围没有识别到道具需求；请确认剧本解析或人工确认结果。")
        if any(item.category == "costume" for item in inventory):
            warnings.append("服装库存已支持人工维护；当前版本尚未从剧本文本自动抽取服装需求。")
        if not inventory_by_name and requirements:
            warnings.append("尚未维护任何道具库存，所有道具都会被标记为缺失。")
        if not scene_id and len(scenes) > 1 and requirements:
            warnings.append("全剧本检查按每种道具至少 1 件计算；具体场次请切换到单场检查。")

        ready_count = sum(item.status == "ready" for item in requirements)
        unavailable_count = len(requirements) - ready_count
        if not requirements:
            summary = "当前范围没有可检查的道具。"
        elif unavailable_count == 0:
            summary = f"{scene_title}：{ready_count} 种道具均已就绪。"
        else:
            summary = f"{scene_title}：{ready_count} 种道具已就绪，{unavailable_count} 种仍需处理。"

        return ResourceCheckResponse(
            script_id=analysis.script_id,
            scene_id=scene_id,
            scene_title=scene_title,
            requirements=requirements,
            ready_count=ready_count,
            missing_count=unavailable_count,
            summary=summary,
            warnings=warnings,
        )
