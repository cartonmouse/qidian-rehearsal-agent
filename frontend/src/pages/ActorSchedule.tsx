import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  FileUp,
  Layers3,
  Loader2,
  Package,
  Save,
  Users,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  confirmScheduleBatch,
  generateScheduleDraft,
  getAvailability,
  getScheduleDraft,
  getScripts,
  overrideSchedule,
  planSchedule,
  saveAvailability,
  type AvailabilitySlot,
  type ScheduleDraft,
  type ScheduleTask,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  formatAvailabilityCsv,
  formatAvailabilityText,
  parseAvailabilityImport,
  parseAvailabilityText,
} from "@/lib/rehearsal";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

const REVIEW_STATUS_LABELS: Record<ScriptSummary["review_status"], string> = {
  pending: "待确认",
  confirmed: "已确认",
  edited: "已修改",
};

const CONFLICT_PRIORITY_LABELS: Record<ScheduleTask["conflict_priority"], string> = {
  none: "无冲突",
  low: "低优先级",
  medium: "中优先级",
  high: "高优先级",
};

const ALTERNATIVE_KIND_LABELS: Record<string, string> = {
  shorten_duration: "缩短时长",
  split_by_actor: "分组排练",
  request_availability: "补充档期",
};

type ScheduleOverridePayload = {
  task_id: string;
  date: string;
  start: string;
  end: string;
  note: string;
};

export default function ActorSchedule() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [schedule, setSchedule] = useState<ScheduleDraft | null>(null);
  const [availabilityText, setAvailabilityText] = useState("");
  const [loading, setLoading] = useState(true);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const availabilityFileRef = useRef<HTMLInputElement>(null);

  const selectedScript = useMemo(
    () => scripts.find((script) => script.script_id === selectedScriptId) || null,
    [scripts, selectedScriptId],
  );
  const previewSlots = useMemo(() => {
    if (!availabilityText.trim()) return [];
    try {
      return parseAvailabilityImport(availabilityText);
    } catch {
      return [];
    }
  }, [availabilityText]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void Promise.all([getScripts(), getAvailability()])
      .then(([scriptItems, slots]) => {
        if (cancelled) return;
        setScripts(scriptItems);
        setSelectedScriptId((current) => (
          current && scriptItems.some((script) => script.script_id === current)
            ? current
            : scriptItems[0]?.script_id || ""
        ));
        setAvailabilityText(formatAvailabilityText(slots));
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "排练数据加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedScriptId) {
      setSchedule(null);
      return;
    }
    let cancelled = false;
    setScheduleLoading(true);
    setError("");
    void getScheduleDraft(selectedScriptId)
      .then((draft) => {
        if (!cancelled) setSchedule(draft);
      })
      .catch((reason) => {
        if (!cancelled) {
          setSchedule(null);
          setError(reason instanceof Error ? reason.message : "排班任务加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setScheduleLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedScriptId]);

  async function importAvailability(file?: File) {
    if (!file) return;
    setImporting(true);
    setError("");
    setMessage("");
    try {
      const imported = parseAvailabilityImport(await file.text());
      setAvailabilityText(formatAvailabilityText(imported));
      setMessage(`已导入 ${imported.length} 条档期记录。请确认预览后点击“保存档期”。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "档期文件解析失败");
    } finally {
      setImporting(false);
      if (availabilityFileRef.current) availabilityFileRef.current.value = "";
    }
  }

  function downloadTemplate() {
    const blob = new Blob([`\uFEFF${formatAvailabilityCsv([])}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "qidian-actor-availability-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function persistAvailability() {
    let slots: AvailabilitySlot[];
    try {
      slots = parseAvailabilityText(availabilityText);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "演员档期格式错误");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveAvailability(slots);
      setAvailabilityText(formatAvailabilityText(saved));
      setMessage(`已保存 ${saved.length} 条演员可用时间。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "演员档期保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function createSchedule() {
    if (!selectedScript) return;
    setScheduleLoading(true);
    setError("");
    setMessage("");
    try {
      const preview = selectedScript.review_status === "pending";
      setSchedule(await generateScheduleDraft(selectedScript.script_id, 45, preview));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练任务生成失败");
    } finally {
      setScheduleLoading(false);
    }
  }

  async function autoPlan() {
    if (!selectedScript) return;
    let slots: AvailabilitySlot[];
    try {
      slots = parseAvailabilityText(availabilityText);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "可用时间格式错误");
      return;
    }
    setPlanning(true);
    setError("");
    setMessage("");
    try {
      setSchedule(await planSchedule(selectedScript.script_id, slots));
      setMessage("自动排班已更新，未排班任务会保留具体原因。 ");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自动排班失败");
    } finally {
      setPlanning(false);
    }
  }

  const scheduledCount = schedule?.tasks.filter((task) => task.status === "scheduled" || task.status === "overridden").length || 0;
  const unassignedCount = schedule?.tasks.filter((task) => task.status === "unassigned").length || 0;

  async function applyScheduleOverride(payload: ScheduleOverridePayload) {
    if (!selectedScript) return;
    setPlanning(true);
    setError("");
    setMessage("");
    try {
      setSchedule(await overrideSchedule(selectedScript.script_id, payload));
      setMessage("已保存导演人工覆盖；该时段会保留为人工决定，不伪装成演员档期校验通过。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "人工覆盖排班失败");
      throw reason;
    } finally {
      setPlanning(false);
    }
  }

  async function confirmScheduledBatch() {
    if (!selectedScript || !schedule) return;
    const overrides = schedule.tasks
      .filter((task) => task.status === "scheduled" && task.scheduled_date && task.scheduled_start && task.scheduled_end)
      .map((task) => ({
        task_id: task.task_id,
        date: task.scheduled_date as string,
        start: task.scheduled_start as string,
        end: task.scheduled_end as string,
        note: "导演批量确认自动排班时段",
      }));
    if (overrides.length === 0) {
      setError("当前没有可批量确认的自动排班任务");
      return;
    }
    setPlanning(true);
    setError("");
    setMessage("");
    try {
      const result = await confirmScheduleBatch(selectedScript.script_id, overrides);
      setSchedule(result.schedule);
      setMessage(`已原子确认 ${result.overridden_count} 个排练任务；人工确认不会伪装成演员档期校验通过。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量确认排班失败");
    } finally {
      setPlanning(false);
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <CalendarClock className="text-primary" size={30} />
            演员排练表
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            独立维护演员档期，查看场次任务，并把共同空闲时间变成可执行的排练安排。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          调度 Agent
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

      <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.72fr)_minmax(560px,1.28fr)]">
        <div className="space-y-4">
          <Card>
            <CardContent className="p-4 md:p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <FileText size={16} className="text-primary" />
                    选择剧本
                  </div>
                  <p className="mt-1 text-xs leading-5 text-dim">
                    排练任务按剧本版本保存。切换剧本不会影响演员时间池。
                  </p>
                </div>
                <span className="rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[10px] text-primary">
                  {scripts.length} 个版本
                </span>
              </div>

              {loading ? (
                <div className="mt-4 h-10 animate-pulse rounded-xl bg-hover" />
              ) : scripts.length > 0 ? (
                <>
                  <select
                    value={selectedScriptId}
                    onChange={(event) => {
                      setSelectedScriptId(event.target.value);
                      setMessage("");
                    }}
                    className="mt-4 h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30"
                    aria-label="选择剧本版本"
                  >
                    {scripts.map((script) => (
                      <option key={script.script_id} value={script.script_id}>
                        {script.title} · {script.version_label}
                      </option>
                    ))}
                  </select>
                  {selectedScript && (
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">
                        {REVIEW_STATUS_LABELS[selectedScript.review_status]}
                      </span>
                      <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{selectedScript.scene_count} 场</span>
                      <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">{selectedScript.character_count} 角色</span>
                    </div>
                  )}
                </>
              ) : (
                <div className="mt-4 rounded-xl border border-border bg-background/40 px-3 py-4 text-sm leading-6 text-dim">
                  还没有已保存的剧本。先到排练工作台运行一次解析 Agent。
                </div>
              )}

              <Button type="button" variant="outline" size="sm" className="mt-4" onClick={() => navigate("/rehearsal")}>
                {scripts.length > 0 ? "回到排练工作台" : "去解析第一个剧本"}
                <ArrowRight size={14} />
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 md:p-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Users size={16} className="text-primary" />
                    演员时间池
                    <span className="rounded-full border border-teal/25 bg-teal/8 px-2 py-0.5 text-[10px] font-normal text-teal">可独立维护</span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-dim">
                    推荐使用 CSV 或 TSV 导入。Excel、WPS、Google Sheets 都可以直接导出；也可以粘贴表格内容。
                  </p>
                </div>
                <input
                  ref={availabilityFileRef}
                  type="file"
                  className="hidden"
                  accept=".csv,.tsv,.txt"
                  onChange={(event) => void importAvailability(event.target.files?.[0])}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => availabilityFileRef.current?.click()} disabled={importing || saving || planning}>
                    {importing ? <Loader2 className="animate-spin" /> : <FileUp size={14} />}
                    导入 CSV/TSV
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={downloadTemplate} disabled={importing || saving}>
                    <Download size={14} />
                    下载模板
                  </Button>
                  <Button type="button" size="sm" onClick={() => void persistAvailability()} disabled={saving || planning || importing}>
                    {saving ? <Loader2 className="animate-spin" /> : <Save size={14} />}
                    保存档期
                  </Button>
                </div>
              </div>
              <Textarea
                value={availabilityText}
                onChange={(event) => {
                  setAvailabilityText(event.target.value);
                  setMessage("");
                  setError("");
                }}
                className="mt-3 min-h-40 rounded-xl font-mono text-xs leading-6"
                placeholder={'演员,日期,开始时间,结束时间\n小林,2026-08-25,19:00,21:00\n导演,2026-08-25,19:00,21:00'}
              />
              <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border bg-background/35 px-3 py-2.5 text-[11px] leading-5 text-dim sm:flex-row sm:items-center sm:justify-between">
                <span>字段顺序：演员、日期、开始时间、结束时间。支持逗号、制表符和竖线分隔。</span>
                <span className="shrink-0 text-primary">当前可识别 {previewSlots.length} 条</span>
              </div>
              {previewSlots.length > 0 && <AvailabilityPreview slots={previewSlots} />}
              <div className="mt-2 text-[11px] leading-5 text-dim">
                导入只会填充本地编辑区，确认预览后点击“保存档期”才会写入时间池。自动排班会寻找同一场次所有演员的共同空闲时间。
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="min-h-[680px] overflow-hidden">
          <CardContent className="h-full p-4 md:p-5">
            {!selectedScript ? (
              <EmptyScheduleState hasScripts={scripts.length > 0} onNavigate={() => navigate("/rehearsal")} />
            ) : scheduleLoading && !schedule ? (
              <div className="flex min-h-[620px] flex-col items-center justify-center text-center">
                <div className="h-12 w-12 animate-pulse rounded-2xl bg-primary/12" />
                <div className="mt-4 text-sm text-dim">正在读取排练任务...</div>
              </div>
            ) : !schedule ? (
              <EmptyScheduleState hasScripts onCreate={() => void createSchedule()} creating={scheduleLoading} />
            ) : (
              <ScheduleOverview
                schedule={schedule}
                selectedScript={selectedScript}
                scheduledCount={scheduledCount}
                unassignedCount={unassignedCount}
                planning={planning}
                onCreate={() => void createSchedule()}
                onPlan={() => void autoPlan()}
                onOverride={applyScheduleOverride}
                onBatchConfirm={() => void confirmScheduledBatch()}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function AvailabilityPreview({ slots }: { slots: AvailabilitySlot[] }) {
  const visibleSlots = slots.slice(0, 5);
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-border bg-background/35">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 text-xs font-semibold">
        <span>档期预览</span>
        <span className="text-[11px] font-normal text-dim">显示前 {visibleSlots.length} 条，共 {slots.length} 条</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[460px] text-left text-[11px]">
          <thead className="text-dim">
            <tr>
              <th className="px-3 py-2 font-medium">演员</th>
              <th className="px-3 py-2 font-medium">日期</th>
              <th className="px-3 py-2 font-medium">开始</th>
              <th className="px-3 py-2 font-medium">结束</th>
            </tr>
          </thead>
          <tbody>
            {visibleSlots.map((slot) => (
              <tr key={`${slot.actor}-${slot.date}-${slot.start}-${slot.end}`} className="border-t border-border/60">
                <td className="px-3 py-2 text-text">{slot.actor}</td>
                <td className="px-3 py-2 text-dim">{slot.date}</td>
                <td className="px-3 py-2 text-dim">{slot.start}</td>
                <td className="px-3 py-2 text-dim">{slot.end}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmptyScheduleState({
  hasScripts,
  creating = false,
  onNavigate,
  onCreate,
}: {
  hasScripts: boolean;
  creating?: boolean;
  onNavigate?: () => void;
  onCreate?: () => void;
}) {
  return (
    <div className="flex min-h-[620px] flex-col items-center justify-center text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary">
        {hasScripts ? <Layers3 size={30} /> : <FileText size={30} />}
      </div>
      <div className="mt-5 text-xl font-semibold">
        {hasScripts ? "还没有排练任务" : "先选择一个剧本"}
      </div>
      <p className="mt-2 max-w-md text-sm leading-6 text-dim">
        {hasScripts
          ? "可以直接在这里生成任务。剧本尚未人工确认时，会先生成标记清晰的调度预览。"
          : "剧本解析完成后，保存结果会出现在左侧选择器中。"}
      </p>
      {hasScripts && onCreate ? (
        <Button type="button" className="mt-5" onClick={onCreate} disabled={creating}>
          {creating ? <Loader2 className="animate-spin" /> : <Layers3 size={14} />}
          生成排练任务
        </Button>
      ) : onNavigate ? (
        <Button type="button" variant="outline" className="mt-5" onClick={onNavigate}>
          去排练工作台
          <ArrowRight size={14} />
        </Button>
      ) : null}
    </div>
  );
}

function ScheduleOverview({
  schedule,
  selectedScript,
  scheduledCount,
  unassignedCount,
  planning,
  onCreate,
  onPlan,
  onOverride,
  onBatchConfirm,
}: {
  schedule: ScheduleDraft;
  selectedScript: ScriptSummary;
  scheduledCount: number;
  unassignedCount: number;
  planning: boolean;
  onCreate: () => void;
  onPlan: () => void;
  onOverride: (payload: ScheduleOverridePayload) => Promise<void>;
  onBatchConfirm: () => void;
}) {
  const parallelCount = new Set(schedule.tasks.map((task) => task.parallel_group)).size;
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            <CalendarClock size={19} className="text-primary" />
            {selectedScript.title}
            {schedule.is_preview && (
              <span className="rounded-full border border-orange/25 bg-orange/10 px-2 py-0.5 text-[10px] font-normal text-orange">未确认预览</span>
            )}
          </div>
          <div className="mt-1 text-xs text-dim">
            版本 {selectedScript.version_label}，任务来自当前剧本结构。
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCreate} disabled={planning}>
            <Layers3 size={14} />
            重新生成任务
          </Button>
          <Button type="button" size="sm" onClick={onPlan} disabled={planning}>
            {planning ? <Loader2 className="animate-spin" /> : <CalendarClock size={14} />}
            自动排班
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onBatchConfirm}
            disabled={planning || !schedule.tasks.some((task) => task.status === "scheduled")}
          >
            <CheckCircle2 size={14} />
            批量确认已排任务
          </Button>
        </div>
      </div>

      {schedule.is_preview && (
        <div className="rounded-xl border border-orange/25 bg-orange/8 px-3 py-2.5 text-xs leading-5 text-orange">
          当前是调度预览。确认或修改剧本场次后，正式任务会以人工确认结果为准。
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="场次任务" value={schedule.tasks.length} tone="primary" />
        <Metric label="并行组" value={parallelCount} tone="teal" />
        <Metric label="已排班" value={scheduledCount} tone="green" />
        <Metric label="待处理" value={unassignedCount} tone="orange" />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {schedule.tasks.map((task) => <TaskCard key={task.task_id} task={task} onOverride={onOverride} />)}
      </div>

      <div className="rounded-xl border border-border bg-background/35 px-3 py-2.5 text-xs leading-5 text-dim">
        自动排班只使用左侧演员时间池。调整档期后再次点击“自动排班”，系统会重新计算所有任务。
      </div>
    </div>
  );
}

function TaskCard({ task, onOverride }: { task: ScheduleTask; onOverride: (payload: ScheduleOverridePayload) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [date, setDate] = useState(task.scheduled_date || "");
  const [start, setStart] = useState(task.scheduled_start || "");
  const [end, setEnd] = useState(task.scheduled_end || "");
  const [note, setNote] = useState(task.manual_override?.note || "");
  const [saving, setSaving] = useState(false);

  function beginOverride() {
    setDate(task.scheduled_date || "");
    setStart(task.scheduled_start || "");
    setEnd(task.scheduled_end || "");
    setNote(task.manual_override?.note || "");
    setEditing(true);
  }

  async function submitOverride() {
    if (!date || !start || !end) return;
    setSaving(true);
    try {
      await onOverride({ task_id: task.task_id, date, start, end, note });
      setEditing(false);
    } catch {
      // The parent renders the server error and keeps this form open for correction.
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-background/45 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-semibold">第 {task.scene_number} 场：{task.title}</div>
        <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">并行组 {task.parallel_group}</span>
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-dim">
        <Clock3 size={13} /> 预计 {task.estimated_minutes} 分钟
      </div>
      <div className="mt-2 text-[11px] leading-5 text-dim">{task.parallel_reason || "按演员和道具资源划分并行组"}</div>
      {task.status === "scheduled" ? (
        <div className="mt-2 rounded-lg bg-green/8 px-2 py-1.5 text-xs text-green">
          已排班：{task.scheduled_date} {task.scheduled_start} 至 {task.scheduled_end}
        </div>
      ) : task.status === "overridden" ? (
        <div className="mt-2 rounded-lg bg-primary/8 px-2 py-1.5 text-xs leading-5 text-primary">
          人工覆盖：{task.scheduled_date} {task.scheduled_start} 至 {task.scheduled_end}
          <div className="text-[11px] text-primary/75">{task.manual_override?.note || "导演已确认该时段"}</div>
        </div>
      ) : task.status === "unassigned" ? (
        <div className="mt-2 rounded-lg bg-red/8 px-2 py-1.5 text-xs leading-5 text-red">
          未排班：{task.unassigned_reason}
        </div>
      ) : (
        <div className="mt-2 rounded-lg bg-hover/60 px-2 py-1.5 text-xs text-dim">
          等待自动排班
        </div>
      )}
      <div className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-dim">
        <Users size={13} className="mt-1 shrink-0 text-teal" />
        <span>{task.required_characters.length > 0 ? task.required_characters.join("、") : "待确认演员"}</span>
      </div>
      <div className="flex items-start gap-1.5 text-xs leading-5 text-dim">
        <Package size={13} className="mt-1 shrink-0 text-orange" />
        <span>{task.props.length > 0 ? task.props.join("、") : "无道具"}</span>
      </div>
      {task.status === "unassigned" && task.alternatives.length > 0 && (
        <div className="mt-3 rounded-lg border border-orange/20 bg-orange/6 p-2.5">
          <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-orange">
            <span>候选替代方案</span>
            <span>{CONFLICT_PRIORITY_LABELS[task.conflict_priority]}</span>
          </div>
          <div className="mt-2 space-y-2">
            {task.alternatives.map((alternative) => (
              <div key={alternative.alternative_id} className="rounded-md bg-background/35 px-2 py-1.5 text-[11px] leading-5 text-dim">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-text">{alternative.label}</span>
                  <span className="rounded-full bg-orange/10 px-1.5 py-0.5 text-[10px] text-orange">{ALTERNATIVE_KIND_LABELS[alternative.kind] || alternative.kind}</span>
                  {alternative.date && <span className="font-mono text-[10px] text-teal">{alternative.date} {alternative.start}–{alternative.end}</span>}
                </div>
                <div>{alternative.reason}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="mt-3 flex justify-end">
        <Button type="button" variant="outline" size="sm" onClick={beginOverride} disabled={saving}>
          {task.status === "overridden" ? "修改人工覆盖" : "人工覆盖排班"}
        </Button>
      </div>
      {editing && (
        <div className="mt-3 rounded-lg border border-primary/20 bg-primary/5 p-2.5">
          <div className="text-[11px] font-medium text-text">导演确认覆盖时段</div>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <label className="text-[10px] text-dim">日期<input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-text" /></label>
            <label className="text-[10px] text-dim">开始<input type="time" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-text" /></label>
            <label className="text-[10px] text-dim">结束<input type="time" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-text" /></label>
          </div>
          <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="覆盖原因（可选）" className="mt-2 w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs text-text placeholder:text-dim" />
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={saving}>取消</Button>
            <Button type="button" size="sm" onClick={() => void submitOverride()} disabled={saving || !date || !start || !end}>
              {saving ? <Loader2 className="animate-spin" /> : <Save size={13} />}
              保存覆盖
            </Button>
          </div>
          <div className="mt-1 text-[10px] leading-4 text-dim">覆盖时长不能少于预计 {task.estimated_minutes} 分钟；保存后会在 Agent 运行记录中留下人工决策。</div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: "primary" | "teal" | "green" | "orange" }) {
  const tones = {
    primary: "bg-primary/10 text-primary",
    teal: "bg-teal/10 text-teal",
    green: "bg-green/10 text-green",
    orange: "bg-orange/10 text-orange",
  };
  return (
    <div className={cn("rounded-xl px-3 py-2.5", tones[tone])}>
      <div className="text-[11px] opacity-80">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
