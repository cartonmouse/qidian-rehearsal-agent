import { useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";

import {
  getBudgetItems,
  getInvoices,
  getMusicTimeline,
  getResourceFinanceSummary,
  saveBudgetItems,
  saveInvoices,
  saveMusicTimeline,
  type BudgetLineItem,
  type InvoiceRecord,
  type MusicTimelineNote,
  type ResourceFinanceSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const INPUT_CLASS = "flex h-9 w-full rounded-lg border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";
const TODAY = new Date().toISOString().slice(0, 10);

const CATEGORY_LABELS: Record<BudgetLineItem["category"], string> = {
  prop: "道具",
  costume: "服装",
  music: "音乐",
  room: "场地",
  transport: "交通",
  promotion: "宣传",
  other: "其他",
};

const CUE_LABELS: Record<MusicTimelineNote["cue_type"], string> = {
  intro: "开场",
  cue: "提示点",
  transition: "转场",
  outro: "收尾",
  other: "其他",
};

const BUDGET_STATUS_LABELS: Record<BudgetLineItem["status"], string> = {
  planned: "计划中",
  committed: "已承诺",
  paid: "已支付",
  cancelled: "已取消",
};

const INVOICE_STATUS_LABELS: Record<InvoiceRecord["status"], string> = {
  pending: "待核验",
  verified: "已核验",
  paid: "已支付",
  rejected: "已驳回",
};

function createId() {
  return crypto.randomUUID().replaceAll("-", "");
}

function createEmptyMusic(): MusicTimelineNote {
  return { note_id: createId(), track_name: "", scene_id: null, cue_type: "cue", start_seconds: 0, end_seconds: null, note: "" };
}

function createEmptyBudget(): BudgetLineItem {
  return { budget_item_id: createId(), category: "other", name: "", estimated_amount: 0, actual_amount: 0, status: "planned", note: "" };
}

function createEmptyInvoice(): InvoiceRecord {
  return { invoice_id: createId(), invoice_no: "", supplier: "", invoice_date: TODAY, category: "other", amount: 0, budget_item_id: null, status: "pending", note: "" };
}

export default function ResourceFinance() {
  const [music, setMusic] = useState<MusicTimelineNote[]>([]);
  const [budget, setBudget] = useState<BudgetLineItem[]>([]);
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([]);
  const [summary, setSummary] = useState<ResourceFinanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<"music" | "budget" | "invoices" | "">("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getMusicTimeline(), getBudgetItems(), getInvoices(), getResourceFinanceSummary()])
      .then(([musicItems, budgetItems, invoiceItems, finance]) => {
        if (cancelled) return;
        setMusic(musicItems);
        setBudget(budgetItems);
        setInvoices(invoiceItems);
        setSummary(finance);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "资源财务数据加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  async function refreshSummary() {
    setSummary(await getResourceFinanceSummary());
  }

  async function persistMusic() {
    setSaving("music");
    setError("");
    setMessage("");
    try {
      const saved = await saveMusicTimeline(music);
      setMusic(saved);
      setMessage(`已保存 ${saved.length} 条配乐时间轴笔记。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "配乐时间轴保存失败");
    } finally {
      setSaving("");
    }
  }

  async function persistBudget() {
    setSaving("budget");
    setError("");
    setMessage("");
    try {
      const saved = await saveBudgetItems(budget);
      setBudget(saved);
      await refreshSummary();
      setMessage(`已保存 ${saved.length} 个预算项目，汇总已更新。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预算保存失败");
    } finally {
      setSaving("");
    }
  }

  async function persistInvoices() {
    setSaving("invoices");
    setError("");
    setMessage("");
    try {
      const saved = await saveInvoices(invoices);
      setInvoices(saved);
      await refreshSummary();
      setMessage(`已保存 ${saved.length} 张发票，关联与核验提示已更新。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发票保存失败");
    } finally {
      setSaving("");
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]"><Archive className="text-primary" size={30} />音乐与预算</div>
          <p className="mt-1 text-sm leading-6 text-dim">记录配乐时间轴、制作预算和发票元数据，让 Resource Agent 解释资源与金额之间的缺口。</p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">Resource Finance Agent</div>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green"><CheckCircle2 size={16} />{message}</div>}

      {loading ? <Card className="min-h-[480px]"><CardContent className="flex min-h-[480px] flex-col items-center justify-center"><Loader2 className="animate-spin text-primary" size={28} /><div className="mt-3 text-sm text-dim">正在读取资源财务档案...</div></CardContent></Card> : <>
        <FinanceSummary summary={summary} />
        <div className="grid gap-4 xl:grid-cols-2">
          <MusicCard music={music} saving={saving === "music"} onAdd={() => setMusic((items) => [...items, createEmptyMusic()])} onRemove={(id) => setMusic((items) => items.filter((item) => item.note_id !== id))} onUpdate={(id, patch) => setMusic((items) => items.map((item) => item.note_id === id ? { ...item, ...patch } : item))} onSave={() => void persistMusic()} />
          <BudgetCard budget={budget} saving={saving === "budget"} onAdd={() => setBudget((items) => [...items, createEmptyBudget()])} onRemove={(id) => setBudget((items) => items.filter((item) => item.budget_item_id !== id))} onUpdate={(id, patch) => setBudget((items) => items.map((item) => item.budget_item_id === id ? { ...item, ...patch } : item))} onSave={() => void persistBudget()} />
        </div>
        <InvoiceCard invoices={invoices} budget={budget} saving={saving === "invoices"} onAdd={() => setInvoices((items) => [...items, createEmptyInvoice()])} onRemove={(id) => setInvoices((items) => items.filter((item) => item.invoice_id !== id))} onUpdate={(id, patch) => setInvoices((items) => items.map((item) => item.invoice_id === id ? { ...item, ...patch } : item))} onSave={() => void persistInvoices()} />
      </>}
    </div>
  );
}

function FinanceSummary({ summary }: { summary: ResourceFinanceSummary | null }) {
  if (!summary) return null;
  return <Card><CardContent className="p-4 md:p-5">
    <div className="flex items-start justify-between gap-3 border-b border-border pb-4"><div><div className="flex items-center gap-2 text-sm font-semibold"><Archive size={16} className="text-primary" />预算与发票概览</div><p className="mt-1 text-xs leading-5 text-dim">发票金额和预算实际金额分开保存，Agent 只提示关联、待核验和超支风险。</p></div><span className={cn("rounded-full px-2.5 py-1 text-xs", summary.variance > 0 ? "bg-red/10 text-red" : "bg-teal/10 text-teal")}>{summary.variance > 0 ? "当前超出预算" : "当前未超预算"}</span></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><FinanceNumber label="预算" value={summary.estimated_total} /><FinanceNumber label="实际" value={summary.actual_total} tone={summary.variance > 0 ? "red" : "text"} /><FinanceNumber label="发票总额" value={summary.invoice_total} tone="teal" /><FinanceNumber label="已核验" value={summary.verified_invoice_total} tone="green" /><FinanceNumber label="未关联" value={summary.unlinked_invoice_total} tone={summary.unlinked_invoice_total > 0 ? "orange" : "text"} /></div>
    {summary.categories.length > 0 && <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[560px] text-left text-xs"><thead className="text-dim"><tr className="border-b border-border"><th className="px-2 py-2 font-medium">类别</th><th className="px-2 py-2 font-medium">预算</th><th className="px-2 py-2 font-medium">实际</th><th className="px-2 py-2 font-medium">发票</th></tr></thead><tbody>{summary.categories.map((item) => <tr key={item.category} className="border-b border-border/50 last:border-0"><td className="px-2 py-2.5 text-text">{CATEGORY_LABELS[item.category as BudgetLineItem["category"]] || item.category}</td><td className="px-2 py-2.5 text-dim">¥{item.estimated_amount.toFixed(2)}</td><td className={cn("px-2 py-2.5", item.actual_amount > item.estimated_amount ? "text-red" : "text-text")}>¥{item.actual_amount.toFixed(2)}</td><td className="px-2 py-2.5 text-dim">¥{item.invoice_amount.toFixed(2)}</td></tr>)}</tbody></table></div>}
    {summary.warnings.length > 0 && <div className="mt-4 space-y-1 rounded-xl border border-orange/20 bg-orange/6 px-3 py-2.5 text-xs leading-5 text-orange">{summary.warnings.map((warning) => <div key={warning}>· {warning}</div>)}</div>}
  </CardContent></Card>;
}

function FinanceNumber({ label, value, tone = "text" }: { label: string; value: number; tone?: "text" | "red" | "teal" | "green" | "orange" }) {
  const tones = { text: "text-text", red: "text-red", teal: "text-teal", green: "text-green", orange: "text-orange" };
  return <div className="rounded-lg bg-background/40 px-3 py-2.5"><div className="text-[11px] text-dim">{label}</div><div className={cn("mt-1 text-lg font-semibold", tones[tone])}>¥{value.toFixed(2)}</div></div>;
}

function MusicCard({ music, saving, onAdd, onRemove, onUpdate, onSave }: { music: MusicTimelineNote[]; saving: boolean; onAdd: () => void; onRemove: (id: string) => void; onUpdate: (id: string, patch: Partial<MusicTimelineNote>) => void; onSave: () => void }) {
  return <Card><CardContent className="p-4 md:p-5"><SectionHeader title="配乐时间轴" count={music.length} description="用秒记录音乐进入、转场和收尾点；备注保留排练时的实际口令。" onAdd={onAdd} onSave={onSave} saving={saving} addLabel="新增时间点" saveLabel="保存时间轴" />
    {music.length === 0 ? <EmptyBlock text="还没有配乐时间轴。先记录一条音乐提示点。" /> : <div className="mt-4 space-y-2">{music.map((item) => <div key={item.note_id} className="rounded-xl border border-border bg-background/30 p-3"><div className="grid gap-2 md:grid-cols-[1.2fr_0.7fr_0.8fr_0.8fr_auto] md:items-end"><Field label="曲目"><Input value={item.track_name} onChange={(event) => onUpdate(item.note_id, { track_name: event.target.value })} placeholder="例如：低频脉冲" /></Field><Field label="场次"><Input value={item.scene_id || ""} onChange={(event) => onUpdate(item.note_id, { scene_id: event.target.value || null })} placeholder="scene-1" /></Field><Field label="类型"><select value={item.cue_type} onChange={(event) => onUpdate(item.note_id, { cue_type: event.target.value as MusicTimelineNote["cue_type"] })} className={INPUT_CLASS}>{Object.entries(CUE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Field label="开始（秒）"><Input type="number" min={0} value={item.start_seconds} onChange={(event) => onUpdate(item.note_id, { start_seconds: Math.max(0, Number(event.target.value) || 0) })} /></Field><Button type="button" variant="ghost" size="icon" className="text-dim hover:text-red" onClick={() => onRemove(item.note_id)} aria-label="删除配乐时间点"><Trash2 size={15} /></Button></div><div className="mt-2 grid gap-2 md:grid-cols-2"><Field label="结束（秒，可选）"><Input type="number" min={0} value={item.end_seconds ?? ""} onChange={(event) => onUpdate(item.note_id, { end_seconds: event.target.value ? Math.max(0, Number(event.target.value)) : null })} /></Field><Field label="排练备注"><Input value={item.note} onChange={(event) => onUpdate(item.note_id, { note: event.target.value })} placeholder="例如：导演说‘灯暗后两拍进’" /></Field></div></div>)}</div>}
  </CardContent></Card>;
}

function BudgetCard({ budget, saving, onAdd, onRemove, onUpdate, onSave }: { budget: BudgetLineItem[]; saving: boolean; onAdd: () => void; onRemove: (id: string) => void; onUpdate: (id: string, patch: Partial<BudgetLineItem>) => void; onSave: () => void }) {
  return <Card><CardContent className="p-4 md:p-5"><SectionHeader title="制作预算" count={budget.length} description="预算项目由剧团人工维护，实际金额不会被发票 Agent 自动覆盖。" onAdd={onAdd} onSave={onSave} saving={saving} addLabel="新增预算" saveLabel="保存预算" />
    {budget.length === 0 ? <EmptyBlock text="还没有预算项目。先添加场地、道具或音乐成本。" /> : <div className="mt-4 space-y-2">{budget.map((item) => <div key={item.budget_item_id} className="rounded-xl border border-border bg-background/30 p-3"><div className="grid gap-2 md:grid-cols-[0.8fr_1.2fr_0.8fr_0.8fr_0.8fr_auto] md:items-end"><Field label="类别"><select value={item.category} onChange={(event) => onUpdate(item.budget_item_id, { category: event.target.value as BudgetLineItem["category"] })} className={INPUT_CLASS}>{Object.entries(CATEGORY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Field label="项目"><Input value={item.name} onChange={(event) => onUpdate(item.budget_item_id, { name: event.target.value })} placeholder="例如：排练室押金" /></Field><Field label="预计金额"><Input type="number" min={0} step="0.01" value={item.estimated_amount} onChange={(event) => onUpdate(item.budget_item_id, { estimated_amount: Math.max(0, Number(event.target.value) || 0) })} /></Field><Field label="实际金额"><Input type="number" min={0} step="0.01" value={item.actual_amount} onChange={(event) => onUpdate(item.budget_item_id, { actual_amount: Math.max(0, Number(event.target.value) || 0) })} /></Field><Field label="状态"><select value={item.status} onChange={(event) => onUpdate(item.budget_item_id, { status: event.target.value as BudgetLineItem["status"] })} className={INPUT_CLASS}>{Object.entries(BUDGET_STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Button type="button" variant="ghost" size="icon" className="text-dim hover:text-red" onClick={() => onRemove(item.budget_item_id)} aria-label="删除预算项目"><Trash2 size={15} /></Button></div><div className="mt-2"><Field label="备注"><Input value={item.note} onChange={(event) => onUpdate(item.budget_item_id, { note: event.target.value })} placeholder="例如：等待剧团报销" /></Field></div></div>)}</div>}
  </CardContent></Card>;
}

function InvoiceCard({ invoices, budget, saving, onAdd, onRemove, onUpdate, onSave }: { invoices: InvoiceRecord[]; budget: BudgetLineItem[]; saving: boolean; onAdd: () => void; onRemove: (id: string) => void; onUpdate: (id: string, patch: Partial<InvoiceRecord>) => void; onSave: () => void }) {
  return <Card><CardContent className="p-4 md:p-5"><SectionHeader title="发票与报销元数据" count={invoices.length} description="当前 MVP 保存发票信息和预算关联，不上传原始票据文件。" onAdd={onAdd} onSave={onSave} saving={saving} addLabel="新增发票" saveLabel="保存发票" />
    {invoices.length === 0 ? <EmptyBlock text="还没有发票记录。先登记一张道具、音乐或场地发票。" /> : <div className="mt-4 space-y-2">{invoices.map((item) => <div key={item.invoice_id} className="rounded-xl border border-border bg-background/30 p-3"><div className="grid gap-2 md:grid-cols-[0.8fr_1fr_0.8fr_0.8fr_0.8fr_auto] md:items-end"><Field label="发票号"><Input value={item.invoice_no} onChange={(event) => onUpdate(item.invoice_id, { invoice_no: event.target.value })} placeholder="可选" /></Field><Field label="供应商"><Input value={item.supplier} onChange={(event) => onUpdate(item.invoice_id, { supplier: event.target.value })} placeholder="例如：XX 文化" /></Field><Field label="日期"><Input type="date" value={item.invoice_date} onChange={(event) => onUpdate(item.invoice_id, { invoice_date: event.target.value })} /></Field><Field label="金额"><Input type="number" min={0} step="0.01" value={item.amount} onChange={(event) => onUpdate(item.invoice_id, { amount: Math.max(0, Number(event.target.value) || 0) })} /></Field><Field label="状态"><select value={item.status} onChange={(event) => onUpdate(item.invoice_id, { status: event.target.value as InvoiceRecord["status"] })} className={INPUT_CLASS}>{Object.entries(INVOICE_STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Button type="button" variant="ghost" size="icon" className="text-dim hover:text-red" onClick={() => onRemove(item.invoice_id)} aria-label="删除发票记录"><Trash2 size={15} /></Button></div><div className="mt-2 grid gap-2 md:grid-cols-2"><Field label="类别"><select value={item.category} onChange={(event) => onUpdate(item.invoice_id, { category: event.target.value as BudgetLineItem["category"] })} className={INPUT_CLASS}>{Object.entries(CATEGORY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Field label="关联预算项目"><select value={item.budget_item_id || ""} onChange={(event) => onUpdate(item.invoice_id, { budget_item_id: event.target.value || null })} className={INPUT_CLASS}><option value="">暂不关联</option>{budget.filter((budgetItem) => budgetItem.status !== "cancelled").map((budgetItem) => <option key={budgetItem.budget_item_id} value={budgetItem.budget_item_id}>{budgetItem.name || "未命名预算"}</option>)}</select></Field></div><div className="mt-2"><Field label="备注"><Input value={item.note} onChange={(event) => onUpdate(item.invoice_id, { note: event.target.value })} placeholder="例如：等待导演核验" /></Field></div></div>)}</div>}
  </CardContent></Card>;
}

function SectionHeader({ title, count, description, onAdd, onSave, saving, addLabel, saveLabel }: { title: string; count: number; description: string; onAdd: () => void; onSave: () => void; saving: boolean; addLabel: string; saveLabel: string }) {
  return <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2 text-sm font-semibold"><FileText size={16} className="text-primary" />{title}<span className="rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[10px] font-normal text-primary">{count} 条</span></div><p className="mt-1 text-xs leading-5 text-dim">{description}</p></div><div className="flex shrink-0 gap-2"><Button type="button" variant="outline" size="sm" onClick={onAdd} disabled={saving}><Plus size={14} />{addLabel}</Button><Button type="button" size="sm" onClick={onSave} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Save size={14} />}{saveLabel}</Button></div></div>;
}

function EmptyBlock({ text }: { text: string }) { return <div className="mt-4 rounded-xl border border-dashed border-border bg-background/35 px-4 py-8 text-center text-sm leading-6 text-dim">{text}</div>; }

function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="block min-w-0"><span className="text-[11px] font-medium text-text">{label}</span><div className="mt-1.5">{children}</div></label>; }
