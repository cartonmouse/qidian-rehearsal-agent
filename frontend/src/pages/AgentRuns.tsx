import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleX,
  Clock3,
  Loader2,
  RefreshCw,
  Workflow,
} from "lucide-react";

import { getAgentRuns, type AgentRunRecord, type AgentStep } from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

const AGENT_LABELS: Record<AgentRunRecord["agent"], string> = {
  "script-analysis": "剧本解读 Agent",
  "schedule-draft": "排练调度 Agent",
  "schedule-plan": "自动排班 Agent",
  "line-reading": "对词 Agent",
  "script-rag": "剧本问答 Agent",
};

const STATUS_LABELS: Record<AgentRunRecord["status"], string> = {
  completed: "已完成",
  fallback: "已降级",
  failed: "失败",
};

function statusClass(status: AgentRunRecord["status"]) {
  if (status === "fallback") return "text-amber-300 bg-amber-300/10 border-amber-300/25";
  if (status === "failed") return "text-red bg-red/10 border-red/25";
  return "text-emerald-300 bg-emerald-300/10 border-emerald-300/25";
}

function StepIcon({ status }: { status: AgentStep["status"] }) {
  if (status === "failed") return <CircleX size={16} className="text-red" />;
  if (status === "repaired") return <AlertTriangle size={16} className="text-amber-300" />;
  return <CheckCircle2 size={16} className="text-emerald-300" />;
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AgentRuns() {
  const [runs, setRuns] = useState<AgentRunRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const items = await getAgentRuns(80);
      setRuns(items);
      setSelectedId((current) => current && items.some((item) => item.run_id === current) ? current : items[0]?.run_id || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Agent 运行记录加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const selected = useMemo(
    () => runs.find((item) => item.run_id === selectedId) || null,
    [runs, selectedId],
  );
  const fallbackCount = runs.filter((item) => item.status === "fallback").length;
  const averageDuration = runs.length
    ? Math.round(runs.reduce((total, item) => total + item.duration_ms, 0) / runs.length)
    : 0;

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Activity className="text-primary" size={30} />
            Agent运行记录
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-dim">
            每次解析、调度、排班、对词和剧本问答都会留下可回看的决策轨迹；降级时也会说明原因。
          </p>
        </div>
        <Button variant="secondary" onClick={() => void loadRuns()} disabled={loading}>
          {loading ? <Loader2 size={16} className="mr-2 animate-spin" /> : <RefreshCw size={16} className="mr-2" />}
          刷新记录
        </Button>
      </header>

      {error && <div className="rounded-xl border border-red/25 bg-red/8 px-4 py-3 text-sm text-red">{error}</div>}

      <div className="grid gap-3 md:grid-cols-3">
        {[
          ["已记录运行", runs.length, "本账号的 Agent 调用"],
          ["发生过降级", fallbackCount, "仍保留可用结果"],
          ["平均耗时", `${averageDuration} ms`, "不含页面加载"],
        ].map(([label, value, note]) => (
          <Card key={String(label)} className="border-border/80 bg-card/80">
            <CardContent className="p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-dim">{label}</p>
              <p className="mt-2 text-2xl font-semibold text-text">{value}</p>
              <p className="mt-1 text-xs text-dim">{note}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid min-h-[520px] gap-4 lg:grid-cols-[minmax(300px,0.8fr)_minmax(0,1.4fr)]">
        <Card className="overflow-hidden border-border/80 bg-card/80">
          <CardContent className="p-0">
            {loading && runs.length === 0 ? (
              <div className="flex min-h-[420px] items-center justify-center text-dim">
                <Loader2 className="mr-2 animate-spin" size={18} /> 正在加载运行记录
              </div>
            ) : runs.length === 0 ? (
              <div className="flex min-h-[420px] flex-col items-center justify-center px-8 text-center">
                <Workflow size={32} className="text-primary" />
                <p className="mt-3 font-medium text-text">还没有 Agent 运行记录</p>
                <p className="mt-1 text-sm leading-6 text-dim">去排练工作台解析一次剧本，或在剧本问答、演员排练表中运行一个 Agent。</p>
              </div>
            ) : (
              <div className="divide-y divide-border/70">
                {runs.map((run) => (
                  <button
                    key={run.run_id}
                    type="button"
                    onClick={() => setSelectedId(run.run_id)}
                    className={cn(
                      "flex w-full items-start gap-3 px-4 py-4 text-left transition-colors hover:bg-hover",
                      selectedId === run.run_id && "bg-primary/8",
                    )}
                  >
                    <div className="mt-0.5 rounded-lg bg-primary/10 p-2 text-primary"><Activity size={16} /></div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-text">{run.action}</p>
                        <ChevronRight size={15} className="shrink-0 text-dim" />
                      </div>
                      <p className="mt-1 truncate text-xs text-dim">{AGENT_LABELS[run.agent]} · {run.script_title || "无绑定剧本"}</p>
                      <div className="mt-2 flex items-center gap-2 text-[11px] text-dim">
                        <span className={cn("rounded-full border px-2 py-0.5", statusClass(run.status))}>{STATUS_LABELS[run.status]}</span>
                        <span>{formatTime(run.created_at)}</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/80 bg-card/80">
          <CardContent className="p-5 md:p-6">
            {!selected ? (
              <div className="flex min-h-[420px] flex-col items-center justify-center text-center text-dim">
                <Clock3 size={28} className="text-primary" />
                <p className="mt-3 text-sm">选择左侧记录查看 Agent 的执行轨迹</p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 border-b border-border/70 pb-5 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-primary">{AGENT_LABELS[selected.agent]}</p>
                    <h2 className="mt-1 text-2xl font-semibold text-text">{selected.action}</h2>
                    <p className="mt-2 text-sm leading-6 text-dim">{selected.summary}</p>
                  </div>
                  <span className={cn("w-fit rounded-full border px-3 py-1 text-xs", statusClass(selected.status))}>{STATUS_LABELS[selected.status]}</span>
                </div>

                <div className="grid gap-3 text-sm sm:grid-cols-3">
                  <div className="rounded-xl bg-muted/30 p-3"><p className="text-xs text-dim">运行模式</p><p className="mt-1 text-text">{selected.mode || "默认"}</p></div>
                  <div className="rounded-xl bg-muted/30 p-3"><p className="text-xs text-dim">运行时间</p><p className="mt-1 text-text">{formatTime(selected.created_at)}</p></div>
                  <div className="rounded-xl bg-muted/30 p-3"><p className="text-xs text-dim">耗时</p><p className="mt-1 text-text">{selected.duration_ms} ms</p></div>
                </div>

                <section>
                  <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text"><Workflow size={16} className="text-primary" />执行轨迹</div>
                  <div className="space-y-2">
                    {selected.trace.map((step, index) => (
                      <div key={`${step.name}-${index}`} className="flex gap-3 rounded-xl border border-border/70 bg-background/30 p-3">
                        <div className="mt-0.5"><StepIcon status={step.status} /></div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium text-text">{index + 1}. {step.name}</span><span className="text-[11px] text-dim">产出 {step.output_count}</span></div>
                          <p className="mt-1 text-xs leading-5 text-dim">{step.summary}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {selected.warnings.length > 0 && (
                  <section className="rounded-xl border border-amber-300/25 bg-amber-300/8 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-amber-200"><AlertTriangle size={16} />需要关注</div>
                    <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-100/80">
                      {selected.warnings.filter(Boolean).map((warning, index) => <li key={`${warning}-${index}`}>· {warning}</li>)}
                    </ul>
                  </section>
                )}

                <p className="text-[11px] text-dim">运行 ID：{selected.run_id} · 记录按账号隔离保存，仅展示结构化摘要与决策轨迹。</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
