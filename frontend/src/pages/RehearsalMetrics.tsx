import { useEffect, useState } from "react";
import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  FileText,
  Loader2,
  NotebookPen,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";

import {
  getRehearsalMetrics,
  type RehearsalMetricItem,
  type RehearsalMetrics as RehearsalMetricsData,
} from "@/api/rehearsal";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const SELECT_CLASS = "flex h-9 rounded-lg border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const ENGINE_LABELS: Record<"rules" | "llm" | "fallback", string> = {
  rules: "本地规则",
  llm: "LLM 镜像",
  fallback: "规则降级",
};

export default function RehearsalMetrics() {
  const [windowDays, setWindowDays] = useState("30");
  const [metrics, setMetrics] = useState<RehearsalMetricsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void getRehearsalMetrics(Number(windowDays))
      .then((result) => {
        if (!cancelled) setMetrics(result);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "排练度量加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [windowDays]);

  const maxSessions = Math.max(...(metrics?.trend.map((item) => item.sessions) || [0]), 1);

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <BarChart3 className="text-primary" size={30} />
            排练度量
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            把每次排练留下的产出、亮点、阻塞和下一步聚合成可回溯的进度信号。
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-dim">
          <CalendarDays size={15} className="text-primary" />
          统计窗口
          <select value={windowDays} onChange={(event) => { setLoading(true); setError(""); setWindowDays(event.target.value); }} className={SELECT_CLASS} aria-label="选择统计窗口">
            <option value="7">最近 7 天</option>
            <option value="30">最近 30 天</option>
            <option value="90">最近 90 天</option>
          </select>
        </label>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><CircleAlert size={16} />{error}</div>}

      {loading ? (
        <Card className="min-h-[580px]">
          <CardContent className="flex h-full min-h-[580px] flex-col items-center justify-center text-center">
            <Loader2 className="animate-spin text-primary" size={28} />
            <div className="mt-3 text-sm text-dim">正在计算排练指标...</div>
          </CardContent>
        </Card>
      ) : metrics ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard icon={<NotebookPen size={17} />} label="排练次数" value={metrics.session_count} hint={`${metrics.from_date} 至 ${metrics.to_date}`} />
            <MetricCard icon={<FileText size={17} />} label="具体产出" value={metrics.output_count} hint={`${metrics.output_coverage.toFixed(1)}% 的排练有产出`} tone="teal" />
            <MetricCard icon={<CircleAlert size={17} />} label="阻塞项" value={metrics.blocker_count} hint={`${metrics.blocker_rate.toFixed(1)}% 的排练出现阻塞`} tone="red" />
            <MetricCard icon={<Users size={17} />} label="参与者" value={metrics.unique_participant_count} hint={`平均每场 ${metrics.average_participants.toFixed(1)} 人`} tone="green" />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
            <Card>
              <CardContent className="p-4 md:p-5">
                <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold"><TrendingUp size={17} className="text-primary" />排练活动趋势</div>
                    <p className="mt-1 text-xs leading-5 text-dim">柱高表示当天归档的排练次数；悬停可查看产出、阻塞和下一步数量。</p>
                  </div>
                  <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">{metrics.window_days} 天</span>
                </div>
                <div className="mt-5 flex h-44 items-end gap-1 overflow-x-auto border-b border-border/70 pb-6">
                  {metrics.trend.map((item) => {
                    const height = item.sessions ? Math.max(12, (item.sessions / maxSessions) * 100) : 3;
                    return (
                      <div key={item.date} className="group flex h-full min-w-5 flex-1 flex-col items-center justify-end" title={`${item.date} · ${item.sessions} 场 · ${item.outputs} 项产出 · ${item.blockers} 个阻塞`}>
                        <div className="flex h-full w-full items-end">
                          <div className={cn("w-full rounded-t-md transition-all", item.sessions ? "bg-primary/75 group-hover:bg-primary" : "bg-hover")} style={{ height: `${height}%` }} />
                        </div>
                        <span className="mt-2 whitespace-nowrap text-[9px] text-dim">{item.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <ProgressMetric label="有具体产出" value={metrics.sessions_with_outputs} total={metrics.session_count} percent={metrics.output_coverage} tone="teal" />
                  <ProgressMetric label="出现阻塞" value={metrics.sessions_with_blockers} total={metrics.session_count} percent={metrics.blocker_rate} tone="red" />
                  <ProgressMetric label="形成下一步" value={metrics.sessions_with_next_actions} total={metrics.session_count} percent={metrics.next_action_rate} tone="orange" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 md:p-5">
                <div className="flex items-center gap-2 border-b border-border pb-4 text-sm font-semibold"><Sparkles size={17} className="text-primary" />Agent 路径</div>
                <div className="mt-4 space-y-3">
                  {Object.entries(metrics.engine_counts).length ? Object.entries(metrics.engine_counts).map(([engine, count]) => (
                    <div key={engine} className="flex items-center justify-between rounded-lg bg-background/45 px-3 py-2.5 text-xs">
                      <span className="text-text">{ENGINE_LABELS[engine as keyof typeof ENGINE_LABELS] || engine}</span>
                      <span className="font-semibold text-primary">{count} 次</span>
                    </div>
                  )) : <EmptyText text="当前窗口还没有镜像记录" />}
                </div>
                <div className="mt-5 rounded-xl border border-primary/15 bg-primary/5 px-3 py-3 text-xs leading-5 text-dim">
                  指标只统计已归档反馈。它展示发生了什么，不替导演判断“排得好不好”；点击“排练复盘”可以回到每一条原始记录。
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <InsightPanel title="高频亮点" icon={<CheckCircle2 size={17} />} items={metrics.top_strengths} tone="green" empty="当前窗口还没有明确亮点" />
            <InsightPanel title="高频阻塞" icon={<CircleAlert size={17} />} items={metrics.top_blockers} tone="red" empty="当前窗口还没有明确阻塞" />
          </div>

          <Card>
            <CardContent className="p-4 md:p-5">
              <div className="flex items-center gap-2 border-b border-border pb-4 text-sm font-semibold"><FileText size={17} className="text-primary" />最近排练记录</div>
              {metrics.recent_sessions.length ? (
                <div className="mt-3 divide-y divide-border/70">
                  {metrics.recent_sessions.map((record) => (
                    <div key={record.record_id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-text">
                          {record.script_title || "独立排练记录"}
                          {record.scene_title && <span className="font-normal text-dim">· {record.scene_title}</span>}
                        </div>
                        <div className="mt-1 text-xs text-dim">{record.rehearsal_date} · {ENGINE_LABELS[record.engine]}</div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 text-[10px]">
                        <span className="rounded-full bg-teal/10 px-2 py-1 text-teal">产出 {record.outputs_count}</span>
                        <span className="rounded-full bg-red/10 px-2 py-1 text-red">阻塞 {record.blockers_count}</span>
                        <span className="rounded-full bg-orange/10 px-2 py-1 text-orange">下一步 {record.next_actions_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <div className="py-10 text-center text-sm text-dim">当前统计窗口没有排练记录，先去“排练复盘”归档一次吧。</div>}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  hint,
  tone = "primary",
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  hint: string;
  tone?: "primary" | "teal" | "red" | "green";
}) {
  const styles = {
    primary: "text-primary bg-primary/10",
    teal: "text-teal bg-teal/10",
    red: "text-red bg-red/10",
    green: "text-green bg-green/10",
  };
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-dim">{label}</span>
          <span className={cn("flex h-8 w-8 items-center justify-center rounded-lg", styles[tone])}>{icon}</span>
        </div>
        <div className="mt-3 text-3xl font-display font-bold text-text">{value}</div>
        <div className="mt-1 truncate text-[11px] text-dim" title={hint}>{hint}</div>
      </CardContent>
    </Card>
  );
}

function ProgressMetric({
  label,
  value,
  total,
  percent,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  percent: number;
  tone: "teal" | "red" | "orange";
}) {
  const styles = {
    teal: "bg-teal",
    red: "bg-red",
    orange: "bg-orange",
  };
  return (
    <div className="rounded-lg bg-background/40 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2 text-xs"><span className="text-dim">{label}</span><span className="font-medium text-text">{value}/{total}</span></div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-hover"><div className={cn("h-full rounded-full transition-all", styles[tone])} style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} /></div>
      <div className="mt-1 text-[10px] text-dim">{percent.toFixed(1)}%</div>
    </div>
  );
}

function InsightPanel({
  title,
  icon,
  items,
  tone,
  empty,
}: {
  title: string;
  icon: React.ReactNode;
  items: RehearsalMetricItem[];
  tone: "green" | "red";
  empty: string;
}) {
  const styles = {
    green: "text-green bg-green/8",
    red: "text-red bg-red/8",
  };
  return (
    <Card>
      <CardContent className="p-4 md:p-5">
        <div className="flex items-center gap-2 border-b border-border pb-4 text-sm font-semibold"><span className={cn("flex h-7 w-7 items-center justify-center rounded-lg", styles[tone])}>{icon}</span>{title}</div>
        {items.length ? <div className="mt-3 space-y-2">{items.map((item) => <div key={item.label} className="flex items-start justify-between gap-3 rounded-lg bg-background/40 px-3 py-2.5 text-xs"><span className="leading-5 text-text">{item.label}</span><span className={cn("shrink-0 rounded-full px-2 py-0.5 font-medium", styles[tone])}>{item.count}</span></div>)}</div> : <EmptyText text={empty} />}
      </CardContent>
    </Card>
  );
}

function EmptyText({ text }: { text: string }) {
  return <div className="py-8 text-center text-xs leading-5 text-dim">{text}</div>;
}
