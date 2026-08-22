import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  Archive,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  DoorOpen,
  FileText,
  History,
  Loader2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  Wrench,
} from "lucide-react";

import {
  checkScriptResources,
  createRoomBooking,
  deleteRoomBooking,
  getResourceInventory,
  getResourceAudits,
  getRoomBookings,
  getScript,
  getScripts,
  saveResourceInventory,
  type ResourceCheckResponse,
  type ResourceAuditRecord,
  type ResourceInventoryItem,
  type RoomBooking,
  type ScriptAnalysis,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const INPUT_CLASS = "mt-1.5 h-9 w-full rounded-lg border border-border bg-input px-2.5 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const CHECK_STATUS_LABELS: Record<ResourceCheckResponse["requirements"][number]["status"], string> = {
  ready: "已就绪",
  missing: "缺失",
  maintenance: "维修中",
};

function createInventoryId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replaceAll("-", "");
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32, "0").slice(0, 32);
}

function createEmptyInventoryItem(): ResourceInventoryItem {
  return {
    resource_id: createInventoryId(),
    category: "prop",
    name: "",
    quantity: 1,
    status: "available",
    location: "",
    notes: "",
  };
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function ResourceManagement() {
  const [inventory, setInventory] = useState<ResourceInventoryItem[]>([]);
  const [audits, setAudits] = useState<ResourceAuditRecord[]>([]);
  const [bookings, setBookings] = useState<RoomBooking[]>([]);
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState("all");
  const [check, setCheck] = useState<ResourceCheckResponse | null>(null);
  const [roomForm, setRoomForm] = useState({
    room_name: "排练室 A",
    date: today(),
    start: "19:00",
    end: "21:00",
    purpose: "剧本排练",
  });
  const [loading, setLoading] = useState(true);
  const [savingInventory, setSavingInventory] = useState(false);
  const [savingRoom, setSavingRoom] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedScript = useMemo(
    () => scripts.find((script) => script.script_id === selectedScriptId) || null,
    [scripts, selectedScriptId],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void Promise.all([getResourceInventory(), getRoomBookings(), getScripts(), getResourceAudits(20)])
      .then(([items, roomItems, scriptItems, auditItems]) => {
        if (cancelled) return;
        setInventory(items);
        setAudits(auditItems);
        setBookings(roomItems);
        setScripts(scriptItems);
        setSelectedScriptId((current) => (
          current && scriptItems.some((item) => item.script_id === current)
            ? current
            : scriptItems[0]?.script_id || ""
        ));
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "资源数据加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshAudits() {
    try {
      setAudits(await getResourceAudits(20));
    } catch {
      // The resource write has already succeeded; the audit panel can refresh later.
    }
  }

  useEffect(() => {
    if (!selectedScriptId) {
      setAnalysis(null);
      setSelectedSceneId("all");
      setCheck(null);
      return;
    }
    let cancelled = false;
    void getScript(selectedScriptId)
      .then((item) => {
        if (cancelled) return;
        setAnalysis(item);
        setSelectedSceneId((current) => (
          current === "all" || item.scenes.some((scene) => scene.scene_id === current)
            ? current
            : "all"
        ));
        setCheck(null);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本详情加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedScriptId]);

  function updateInventory(resourceId: string, patch: Partial<ResourceInventoryItem>) {
    setInventory((items) => items.map((item) => (
      item.resource_id === resourceId ? { ...item, ...patch } : item
    )));
    setMessage("");
    setError("");
  }

  function addInventoryItem() {
    setInventory((items) => [...items, createEmptyInventoryItem()]);
    setMessage("");
  }

  function removeInventoryItem(resourceId: string) {
    setInventory((items) => items.filter((item) => item.resource_id !== resourceId));
    setMessage("库存行已移除；点击保存库存后才会写入。");
  }

  async function persistInventory() {
    if (inventory.some((item) => !item.name.trim())) {
      setError("请先补全每条库存记录的资源名称，或移除空白行。");
      return;
    }
    setSavingInventory(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveResourceInventory(inventory);
      setInventory(saved);
      await refreshAudits();
      setMessage(`已保存 ${saved.length} 条库存记录。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "资源库存保存失败");
    } finally {
      setSavingInventory(false);
    }
  }

  async function submitRoomBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingRoom(true);
    setError("");
    setMessage("");
    try {
      const booking = await createRoomBooking(roomForm);
      setBookings((items) => [...items, booking].sort((a, b) => (
        `${a.date}${a.start}${a.room_name}`.localeCompare(`${b.date}${b.start}${b.room_name}`)
      )));
      await refreshAudits();
      setMessage(`已预约 ${booking.room_name}：${booking.date} ${booking.start}-${booking.end}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练室预约失败");
    } finally {
      setSavingRoom(false);
    }
  }

  async function removeBooking(bookingId: string) {
    setError("");
    try {
      await deleteRoomBooking(bookingId);
      setBookings((items) => items.filter((item) => item.booking_id !== bookingId));
      await refreshAudits();
      setMessage("排练室预约已取消。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练室预约删除失败");
    }
  }

  async function runResourceCheck() {
    if (!selectedScriptId) return;
    setChecking(true);
    setError("");
    setMessage("");
    try {
      const result = await checkScriptResources(
        selectedScriptId,
        selectedSceneId === "all" ? null : selectedSceneId,
      );
      setCheck(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "道具资源检查失败");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Archive className="text-primary" size={30} />
            资源管理
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            维护道具与服装库存，预约排练室，并在排练前让 Resource Agent 检查道具是否就绪。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          Resource Agent
        </div>
      </header>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}
      {message && (
        <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green">
          <CheckCircle2 size={16} />
          {message}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(560px,1.15fr)_minmax(360px,0.85fr)]">
        <InventoryCard
          inventory={inventory}
          loading={loading}
          saving={savingInventory}
          onAdd={addInventoryItem}
          onRemove={removeInventoryItem}
          onUpdate={updateInventory}
          onSave={() => void persistInventory()}
        />
        <RoomBookingCard
          bookings={bookings}
          form={roomForm}
          saving={savingRoom}
          onChange={(patch) => setRoomForm((current) => ({ ...current, ...patch }))}
          onSubmit={submitRoomBooking}
          onRemove={(bookingId) => void removeBooking(bookingId)}
        />
      </div>

      <ResourceCheckCard
        scripts={scripts}
        analysis={analysis}
        selectedScript={selectedScript}
        selectedScriptId={selectedScriptId}
        selectedSceneId={selectedSceneId}
        result={check}
        checking={checking}
        onScriptChange={(scriptId) => {
          setSelectedScriptId(scriptId);
          setCheck(null);
          setError("");
        }}
        onSceneChange={(sceneId) => {
          setSelectedSceneId(sceneId);
          setCheck(null);
        }}
        onCheck={() => void runResourceCheck()}
      />

      <ResourceAuditCard audits={audits} />
    </div>
  );
}

function InventoryCard({
  inventory,
  loading,
  saving,
  onAdd,
  onRemove,
  onUpdate,
  onSave,
}: {
  inventory: ResourceInventoryItem[];
  loading: boolean;
  saving: boolean;
  onAdd: () => void;
  onRemove: (resourceId: string) => void;
  onUpdate: (resourceId: string, patch: Partial<ResourceInventoryItem>) => void;
  onSave: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 md:p-5">
        <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Archive size={16} className="text-primary" />
              道具 / 服装库存
              <span className="rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[10px] font-normal text-primary">
                {inventory.length} 条记录
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-dim">库存是 Agent 检查时的人工确认来源；数量为 0 也可以保留缺失记录。</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onAdd} disabled={saving}>
              <Plus size={14} />
              新增资源
            </Button>
            <Button type="button" size="sm" onClick={onSave} disabled={saving || loading}>
              {saving ? <Loader2 className="animate-spin" /> : <Save size={14} />}
              保存库存
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="mt-4 space-y-2">
            <div className="h-12 animate-pulse rounded-xl bg-hover" />
            <div className="h-12 animate-pulse rounded-xl bg-hover" />
          </div>
        ) : inventory.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-border bg-background/35 px-4 py-8 text-center text-sm leading-6 text-dim">
            还没有库存记录。先新增一件道具或服装，Resource Agent 才能给出就绪检查。
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {inventory.map((item) => (
              <div key={item.resource_id} className="rounded-xl border border-border bg-background/30 p-3">
                <div className="grid gap-2 md:grid-cols-[0.8fr_1.35fr_0.55fr_0.85fr_auto] md:items-end">
                  <Field label="类别">
                    <select
                      value={item.category}
                      onChange={(event) => onUpdate(item.resource_id, { category: event.target.value as ResourceInventoryItem["category"] })}
                      className={INPUT_CLASS}
                      aria-label={`${item.name || "资源"}类别`}
                    >
                      <option value="prop">道具</option>
                      <option value="costume">服装</option>
                    </select>
                  </Field>
                  <Field label="名称">
                    <input
                      value={item.name}
                      onChange={(event) => onUpdate(item.resource_id, { name: event.target.value })}
                      className={INPUT_CLASS}
                      placeholder="例如：手电筒"
                      aria-label="资源名称"
                    />
                  </Field>
                  <Field label="数量">
                    <input
                      type="number"
                      min={0}
                      value={item.quantity}
                      onChange={(event) => onUpdate(item.resource_id, { quantity: Math.max(0, Number(event.target.value) || 0) })}
                      className={INPUT_CLASS}
                      aria-label="资源数量"
                    />
                  </Field>
                  <Field label="状态">
                    <select
                      value={item.status}
                      onChange={(event) => onUpdate(item.resource_id, { status: event.target.value as ResourceInventoryItem["status"] })}
                      className={INPUT_CLASS}
                      aria-label="资源状态"
                    >
                      <option value="available">可用</option>
                      <option value="maintenance">维修中</option>
                      <option value="missing">缺失</option>
                    </select>
                  </Field>
                  <Button type="button" variant="ghost" size="icon" className="mt-1 text-dim hover:text-red md:mb-0.5" onClick={() => onRemove(item.resource_id)} aria-label="移除库存记录">
                    <Trash2 size={15} />
                  </Button>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <Field label="存放位置">
                    <input
                      value={item.location}
                      onChange={(event) => onUpdate(item.resource_id, { location: event.target.value })}
                      className={INPUT_CLASS}
                      placeholder="例如：道具柜 2 层"
                    />
                  </Field>
                  <Field label="备注">
                    <input
                      value={item.notes}
                      onChange={(event) => onUpdate(item.resource_id, { notes: event.target.value })}
                      className={INPUT_CLASS}
                      placeholder="例如：需要更换电池"
                    />
                  </Field>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RoomBookingCard({
  bookings,
  form,
  saving,
  onChange,
  onSubmit,
  onRemove,
}: {
  bookings: RoomBooking[];
  form: Omit<RoomBooking, "booking_id">;
  saving: boolean;
  onChange: (patch: Partial<Omit<RoomBooking, "booking_id">>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRemove: (bookingId: string) => void;
}) {
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><DoorOpen size={16} className="text-primary" />排练室预约</div>
            <p className="mt-1 text-xs leading-5 text-dim">同一房间、同一天的重叠时间会被后端拒绝，避免多人同时占用。</p>
          </div>
          <CalendarDays size={18} className="text-dim" />
        </div>
        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="房间">
              <input value={form.room_name} onChange={(event) => onChange({ room_name: event.target.value })} className={INPUT_CLASS} required />
            </Field>
            <Field label="日期">
              <input type="date" value={form.date} onChange={(event) => onChange({ date: event.target.value })} className={INPUT_CLASS} required />
            </Field>
            <Field label="开始">
              <input type="time" value={form.start} onChange={(event) => onChange({ start: event.target.value })} className={INPUT_CLASS} required />
            </Field>
            <Field label="结束">
              <input type="time" value={form.end} onChange={(event) => onChange({ end: event.target.value })} className={INPUT_CLASS} required />
            </Field>
          </div>
          <Field label="用途">
            <input value={form.purpose} onChange={(event) => onChange({ purpose: event.target.value })} className={INPUT_CLASS} placeholder="例如：第一场走位" />
          </Field>
          <Button type="submit" className="w-full" disabled={saving}>
            {saving ? <Loader2 className="animate-spin" /> : <CalendarDays size={14} />}
            {saving ? "正在预约" : "预约排练室"}
          </Button>
        </form>

        <div className="mt-5 border-t border-border pt-4">
          <div className="flex items-center justify-between gap-2 text-xs font-semibold">
            <span>已预约</span>
            <span className="text-dim">{bookings.length} 条</span>
          </div>
          {bookings.length === 0 ? (
            <div className="mt-3 rounded-xl border border-dashed border-border bg-background/35 px-3 py-4 text-center text-xs text-dim">暂无排练室预约</div>
          ) : (
            <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
              {bookings.map((booking) => (
                <div key={booking.booking_id} className="flex items-start justify-between gap-3 rounded-xl border border-border bg-background/35 px-3 py-2.5 text-xs">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-text">{booking.room_name} · {booking.purpose || "排练"}</div>
                    <div className="mt-1 text-dim">{booking.date} · {booking.start}-{booking.end}</div>
                  </div>
                  <button type="button" className="shrink-0 text-dim transition-colors hover:text-red" onClick={() => onRemove(booking.booking_id)} aria-label={`取消 ${booking.room_name} 预约`}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ResourceCheckCard({
  scripts,
  analysis,
  selectedScript,
  selectedScriptId,
  selectedSceneId,
  result,
  checking,
  onScriptChange,
  onSceneChange,
  onCheck,
}: {
  scripts: ScriptSummary[];
  analysis: ScriptAnalysis | null;
  selectedScript: ScriptSummary | null;
  selectedScriptId: string;
  selectedSceneId: string;
  result: ResourceCheckResponse | null;
  checking: boolean;
  onScriptChange: (scriptId: string) => void;
  onSceneChange: (sceneId: string) => void;
  onCheck: () => void;
}) {
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><ClipboardCheck size={16} className="text-primary" />排练前道具就绪检查</div>
            <p className="mt-1 text-xs leading-5 text-dim">Agent 只读取已保存剧本的场次道具和当前库存，不替导演猜测服装需求。</p>
          </div>
          <span className="rounded-full border border-teal/25 bg-teal/8 px-2 py-1 text-[10px] text-teal">可解释匹配</span>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
          <Field label="剧本版本">
            <select value={selectedScriptId} onChange={(event) => onScriptChange(event.target.value)} className={INPUT_CLASS} aria-label="选择资源检查剧本">
              <option value="">选择剧本版本</option>
              {scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label}</option>)}
            </select>
          </Field>
          <Field label="检查范围">
            <select value={selectedSceneId} onChange={(event) => onSceneChange(event.target.value)} className={INPUT_CLASS} disabled={!analysis} aria-label="选择资源检查范围">
              <option value="all">全剧本（每种道具至少 1 件）</option>
              {analysis?.scenes.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>第 {scene.number} 场 · {scene.title}</option>)}
            </select>
          </Field>
          <Button type="button" onClick={onCheck} disabled={!selectedScript || checking}>
            {checking ? <Loader2 className="animate-spin" /> : <ShieldCheck size={14} />}
            {checking ? "检查中" : "开始检查"}
          </Button>
        </div>

        {!selectedScript ? (
          <div className="mt-4 rounded-xl border border-dashed border-border bg-background/35 px-4 py-7 text-center text-sm leading-6 text-dim">
            还没有可检查的剧本。先在排练工作台解析并保存一个剧本版本。
          </div>
        ) : !result ? (
          <div className="mt-4 flex items-center gap-3 rounded-xl border border-border bg-background/35 px-4 py-4 text-sm text-dim">
            <FileText size={17} className="text-primary" />
            选择范围后点击“开始检查”，Agent 会列出每件道具的需求数量、可用数量和处理原因。
          </div>
        ) : (
          <ResourceCheckResult result={result} />
        )}
      </CardContent>
    </Card>
  );
}

function ResourceCheckResult({ result }: { result: ResourceCheckResponse }) {
  return (
    <div className="mt-4">
      <div className="flex flex-col gap-2 rounded-xl border border-primary/20 bg-primary/6 px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div className="text-sm font-medium text-text">{result.summary}</div>
        <div className="flex gap-2 text-[11px]">
          <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">已就绪 {result.ready_count}</span>
          <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">待处理 {result.missing_count}</span>
        </div>
      </div>
      {result.requirements.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {result.requirements.map((item) => (
            <div key={item.name} className="rounded-xl border border-border bg-background/35 px-3 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
                  {item.status === "ready" ? <CheckCircle2 size={15} className="shrink-0 text-teal" /> : item.status === "maintenance" ? <Wrench size={15} className="shrink-0 text-orange" /> : <AlertTriangle size={15} className="shrink-0 text-red" />}
                  <span className="truncate">{item.name}</span>
                </div>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px]", item.status === "ready" ? "bg-teal/10 text-teal" : item.status === "maintenance" ? "bg-orange/10 text-orange" : "bg-red/10 text-red")}>
                  {CHECK_STATUS_LABELS[item.status]}
                </span>
              </div>
              <div className="mt-2 text-xs text-dim">需求 {item.required_quantity} · 可用 {item.available_quantity}</div>
              <div className="mt-1 text-[11px] leading-5 text-dim/80">{item.note}</div>
            </div>
          ))}
        </div>
      )}
      {result.warnings.length > 0 && (
        <div className="mt-3 space-y-1.5 rounded-xl border border-orange/20 bg-orange/6 px-3 py-2.5 text-xs leading-5 text-orange">
          {result.warnings.map((warning) => <div key={warning}>· {warning}</div>)}
        </div>
      )}
    </div>
  );
}

const AUDIT_RESOURCE_LABELS: Record<ResourceAuditRecord["resource_type"], string> = {
  inventory: "库存",
  room: "排练室预约",
  music: "配乐时间轴",
  budget: "预算",
  invoice: "发票",
};

const AUDIT_CHANGE_LABELS: Record<ResourceAuditRecord["changes"][number]["change_type"], string> = {
  created: "新增",
  updated: "修改",
  deleted: "删除",
};

function ResourceAuditCard({ audits }: { audits: ResourceAuditRecord[] }) {
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-text"><History size={16} className="text-primary" />资源变更记录</div>
            <p className="mt-1 text-xs leading-5 text-dim">保留库存、排练室、配乐、预算和发票的最近变更，方便解释 Resource Agent 使用了哪一版人工确认数据。</p>
          </div>
          <span className="rounded-full border border-primary/20 bg-primary/8 px-2 py-1 text-[10px] text-primary">{audits.length} 条</span>
        </div>

        {audits.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-border bg-background/35 px-4 py-6 text-center text-sm text-dim">保存一次库存或资源信息后，这里会显示变更摘要。</div>
        ) : (
          <div className="mt-3 divide-y divide-border/70">
            {audits.map((audit) => (
              <div key={audit.audit_id} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-text">
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">{AUDIT_RESOURCE_LABELS[audit.resource_type]}</span>
                    {audit.summary}
                  </div>
                  <span className="text-[11px] text-dim">{new Date(audit.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {audit.changes.slice(0, 8).map((change) => (
                    <span key={`${audit.audit_id}-${change.resource_id}`} className={cn("rounded-full px-2 py-1 text-[10px]", change.change_type === "created" ? "bg-green/10 text-green" : change.change_type === "deleted" ? "bg-red/10 text-red" : "bg-orange/10 text-orange")}>
                      {AUDIT_CHANGE_LABELS[change.change_type]} {change.label}{change.changed_fields.length > 0 ? ` · ${change.changed_fields.join("、")}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="text-[11px] font-medium text-text">{label}</span>
      {children}
    </label>
  );
}
