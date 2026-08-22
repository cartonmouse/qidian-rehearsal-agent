"""预算与发票 Agent：做金额汇总，并解释预算与票据之间的缺口。"""

from __future__ import annotations

from collections import defaultdict

from backend.rehearsal.models import (
    BudgetCategorySummary,
    BudgetLineItem,
    InvoiceRecord,
    ResourceFinanceSummary,
)


_CATEGORIES = ("prop", "costume", "music", "room", "transport", "promotion", "other")


def _money(value: float) -> float:
    return round(float(value), 2)


class ResourceFinanceAgent:
    """Aggregate finance records without silently treating invoices as payments."""

    def summarize(
        self,
        budget_items: list[BudgetLineItem],
        invoices: list[InvoiceRecord],
    ) -> ResourceFinanceSummary:
        active_items = [item for item in budget_items if item.status != "cancelled"]
        valid_budget_ids = {item.budget_item_id for item in active_items}
        accepted_invoices = [invoice for invoice in invoices if invoice.status != "rejected"]

        estimated_total = _money(sum(item.estimated_amount for item in active_items))
        actual_total = _money(sum(item.actual_amount for item in active_items))
        invoice_total = _money(sum(invoice.amount for invoice in accepted_invoices))
        verified_invoice_total = _money(
            sum(invoice.amount for invoice in accepted_invoices if invoice.status in {"verified", "paid"})
        )
        linked_invoice_total = _money(
            sum(invoice.amount for invoice in accepted_invoices if invoice.budget_item_id in valid_budget_ids)
        )
        unlinked_invoice_total = _money(invoice_total - linked_invoice_total)

        category_values: dict[str, dict[str, float]] = defaultdict(lambda: {
            "estimated_amount": 0.0,
            "actual_amount": 0.0,
            "invoice_amount": 0.0,
        })
        for item in active_items:
            category_values[item.category]["estimated_amount"] += item.estimated_amount
            category_values[item.category]["actual_amount"] += item.actual_amount
        for invoice in accepted_invoices:
            category_values[invoice.category]["invoice_amount"] += invoice.amount

        categories = [
            BudgetCategorySummary(
                category=category,
                estimated_amount=_money(values["estimated_amount"]),
                actual_amount=_money(values["actual_amount"]),
                invoice_amount=_money(values["invoice_amount"]),
            )
            for category in _CATEGORIES
            if category in category_values
            for values in [category_values[category]]
        ]

        warnings: list[str] = []
        if actual_total > estimated_total:
            warnings.append(f"当前实际金额已超出预算 {_money(actual_total - estimated_total):.2f} 元，请人工确认。")
        if unlinked_invoice_total > 0:
            unlinked_count = sum(
                invoice.budget_item_id not in valid_budget_ids
                for invoice in accepted_invoices
            )
            warnings.append(f"有 {unlinked_count} 张发票未关联预算项目，共 {_money(unlinked_invoice_total):.2f} 元。")
        if any(invoice.status == "pending" for invoice in accepted_invoices):
            warnings.append("仍有待核验发票；发票金额不会自动写入预算项目的实际金额。")

        return ResourceFinanceSummary(
            estimated_total=estimated_total,
            actual_total=actual_total,
            invoice_total=invoice_total,
            verified_invoice_total=verified_invoice_total,
            linked_invoice_total=linked_invoice_total,
            unlinked_invoice_total=unlinked_invoice_total,
            variance=_money(actual_total - estimated_total),
            categories=categories,
            warnings=warnings,
            note="预算实际金额与发票金额分开统计；Agent 只提示关联和超支风险，不替人工确认付款事实。",
        )
