"""资源检查 Agent：把剧本道具需求和人工维护的库存做可解释匹配。"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from collections import Counter, defaultdict
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from backend.rehearsal.models import (
    CostumeCheckoutRequest,
    CostumeReturnRequest,
    ResourceAuditChange,
    ResourceAuditRecord,
    ResourceCheckResponse,
    ResourceInventoryItem,
    ResourceRequirement,
    RoomBooking,
    RoomBookingRequest,
    ScriptAnalysis,
)

ResourceAuditType = Literal["inventory", "room", "music", "budget", "invoice"]
ResourceAuditOperation = Literal["replace", "create", "delete", "checkout", "return"]

_AUDIT_ID_FIELDS: dict[str, str] = {
    "inventory": "resource_id",
    "room": "booking_id",
    "music": "note_id",
    "budget": "budget_item_id",
    "invoice": "invoice_id",
}
_AUDIT_LABEL_FIELDS: dict[str, str] = {
    "inventory": "name",
    "room": "room_name",
    "music": "track_name",
    "budget": "name",
    "invoice": "supplier",
}
_AUDIT_FIELD_LABELS = {
    "category": "类别",
    "name": "名称",
    "quantity": "数量",
    "status": "状态",
    "location": "存放位置",
    "notes": "备注",
    "borrowed_quantity": "已借出数量",
    "checked_out_to": "持有人",
    "checked_out_scene_id": "借出场次 ID",
    "checked_out_scene_label": "借出场次",
    "expected_return_date": "预计归还日期",
    "expected_return_time": "预计归还时间",
    "custody_note": "借还备注",
    "room_name": "排练室",
    "date": "日期",
    "start": "开始时间",
    "end": "结束时间",
    "purpose": "用途",
    "track_name": "配乐",
    "scene_id": "场次",
    "cue_type": "提示类型",
    "start_seconds": "开始秒数",
    "end_seconds": "结束秒数",
    "note": "备注",
    "estimated_amount": "预算金额",
    "actual_amount": "实际金额",
    "invoice_no": "发票号码",
    "supplier": "供应商",
    "invoice_date": "发票日期",
    "amount": "发票金额",
    "budget_item_id": "关联预算",
}


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
            if analysis.costumes:
                warnings.append("已读取剧本服装需求；调度 Agent 会继续按库存容量复核服装并行占用。")
            else:
                warnings.append("已维护服装库存，但当前剧本没有识别到服装需求；如有换装请在人工确认节点补充。")
        borrowed_costumes = [item for item in inventory if item.category == "costume" and item.borrowed_quantity > 0]
        if borrowed_costumes:
            labels = "、".join(
                f"{item.name}（{item.borrowed_quantity} 件，{item.checked_out_to or '未记录持有人'}"
                f"{f'，{item.checked_out_scene_label}' if item.checked_out_scene_label else ''}）"
                for item in borrowed_costumes
            )
            warnings.append(f"服装当前存在借出状态：{labels}；排班容量已扣除借出数量，请核对归还时间。")
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


class CostumeCustodyAgent:
    """Apply deterministic, auditable checkout and return state transitions."""

    def checkout(
        self,
        inventory: list[ResourceInventoryItem],
        resource_id: str,
        request: CostumeCheckoutRequest,
    ) -> ResourceInventoryItem:
        item = self._find(inventory, resource_id)
        if item.category != "costume":
            raise ValueError("只有服装库存支持借出")
        if item.status != "available":
            raise ValueError(f"服装“{item.name}”当前状态为 {item.status}，不能借出")
        available_quantity = item.quantity - item.borrowed_quantity
        if request.quantity > available_quantity:
            raise ValueError(f"服装“{item.name}”可借出数量仅剩 {available_quantity} 件")

        if item.borrowed_quantity > 0:
            if self._normalize(item.checked_out_to) != self._normalize(request.holder):
                raise ValueError(f"服装“{item.name}”已有借出记录，持有人为 {item.checked_out_to}")
            if item.checked_out_scene_id and request.scene_id and item.checked_out_scene_id != request.scene_id:
                raise ValueError(f"服装“{item.name}”已有借出场次，不能同时登记给不同场次")
            if (
                item.checked_out_scene_label
                and request.scene_label
                and self._normalize(item.checked_out_scene_label) != self._normalize(request.scene_label)
            ):
                raise ValueError(f"服装“{item.name}”已有借出场次，不能同时登记给不同场次")

        return item.model_copy(update={
            "borrowed_quantity": item.borrowed_quantity + request.quantity,
            "checked_out_to": request.holder,
            "checked_out_scene_id": request.scene_id or item.checked_out_scene_id,
            "checked_out_scene_label": request.scene_label or item.checked_out_scene_label,
            "expected_return_date": request.expected_return_date or item.expected_return_date,
            "expected_return_time": request.expected_return_time or item.expected_return_time,
            "custody_note": request.note or item.custody_note,
        })

    def return_item(
        self,
        inventory: list[ResourceInventoryItem],
        resource_id: str,
        request: CostumeReturnRequest,
    ) -> ResourceInventoryItem:
        item = self._find(inventory, resource_id)
        if item.category != "costume":
            raise ValueError("只有服装库存支持归还")
        if item.borrowed_quantity <= 0:
            raise ValueError(f"服装“{item.name}”当前没有借出数量")
        return_quantity = request.quantity or item.borrowed_quantity
        if return_quantity > item.borrowed_quantity:
            raise ValueError(f"服装“{item.name}”最多只能归还 {item.borrowed_quantity} 件")

        remaining = item.borrowed_quantity - return_quantity
        update = {"borrowed_quantity": remaining}
        if request.note:
            update["custody_note"] = request.note
        if remaining == 0:
            update.update({
                "checked_out_to": "",
                "checked_out_scene_id": None,
                "checked_out_scene_label": "",
                "expected_return_date": None,
                "expected_return_time": None,
                "custody_note": request.note,
            })
        return item.model_copy(update=update)

    @staticmethod
    def _find(inventory: list[ResourceInventoryItem], resource_id: str) -> ResourceInventoryItem:
        item = next((candidate for candidate in inventory if candidate.resource_id == resource_id), None)
        if item is None:
            raise LookupError("库存记录不存在")
        return item

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()


class ResourceAuditAgent:
    """Compare resource snapshots and explain exactly what changed."""

    def compare(
        self,
        *,
        resource_type: ResourceAuditType,
        operation: ResourceAuditOperation,
        before: list[BaseModel],
        after: list[BaseModel],
    ) -> ResourceAuditRecord | None:
        id_field = _AUDIT_ID_FIELDS[resource_type]
        before_by_id = self._index(before, id_field)
        after_by_id = self._index(after, id_field)
        changes: list[ResourceAuditChange] = []

        for resource_id in sorted(set(before_by_id) | set(after_by_id)):
            old_payload = before_by_id.get(resource_id)
            new_payload = after_by_id.get(resource_id)
            if old_payload is None and new_payload is not None:
                label = self._label(resource_type, new_payload)
                changes.append(ResourceAuditChange(
                    change_type="created",
                    resource_id=resource_id,
                    label=label,
                    changed_fields=self._field_labels(new_payload, id_field),
                    summary=f"新增{label}",
                ))
                continue
            if new_payload is None and old_payload is not None:
                label = self._label(resource_type, old_payload)
                changes.append(ResourceAuditChange(
                    change_type="deleted",
                    resource_id=resource_id,
                    label=label,
                    changed_fields=self._field_labels(old_payload, id_field),
                    summary=f"删除{label}",
                ))
                continue
            assert old_payload is not None and new_payload is not None
            fields = [
                key for key in sorted(set(old_payload) | set(new_payload))
                if key != id_field and old_payload.get(key) != new_payload.get(key)
            ]
            if fields:
                label = self._label(resource_type, new_payload)
                field_labels = [self._field_label(field) for field in fields]
                changes.append(ResourceAuditChange(
                    change_type="updated",
                    resource_id=resource_id,
                    label=label,
                    changed_fields=field_labels,
                    summary=f"更新{label}：" + "、".join(field_labels),
                ))

        if not changes:
            return None
        counts = Counter(change.change_type for change in changes)
        summary_parts = []
        if counts["created"]:
            summary_parts.append(f"新增 {counts['created']} 条")
        if counts["updated"]:
            summary_parts.append(f"修改 {counts['updated']} 条")
        if counts["deleted"]:
            summary_parts.append(f"删除 {counts['deleted']} 条")
        resource_label = {
            "inventory": "库存",
            "room": "排练室预约",
            "music": "配乐时间轴",
            "budget": "预算",
            "invoice": "发票",
        }[resource_type]
        operation_label = {"checkout": "借出", "return": "归还"}.get(operation)
        summary_prefix = f"{resource_label}{operation_label}" if operation_label else f"{resource_label}变更"
        return ResourceAuditRecord(
            audit_id=uuid4().hex,
            resource_type=resource_type,
            operation=operation,
            changed_count=len(changes),
            changes=changes,
            summary=f"{summary_prefix}：" + "、".join(summary_parts) + "。",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _index(items: list[BaseModel], id_field: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for item in items:
            payload = item.model_dump(mode="json")
            resource_id = payload.get(id_field)
            if resource_id:
                result[str(resource_id)] = payload
        return result

    @staticmethod
    def _label(resource_type: ResourceAuditType, payload: dict) -> str:
        field = _AUDIT_LABEL_FIELDS[resource_type]
        return str(payload.get(field) or "未命名资源")

    @staticmethod
    def _field_label(field: str) -> str:
        return _AUDIT_FIELD_LABELS.get(field, field)

    @classmethod
    def _field_labels(cls, payload: dict, id_field: str) -> list[str]:
        return [cls._field_label(field) for field in sorted(payload) if field != id_field]
