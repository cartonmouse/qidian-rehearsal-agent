import { useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  History,
  Loader2,
  MessageSquareText,
  NotebookPen,
  Sparkles,
  Users,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  createRehearsalFeedback,
  getRehearsalFeedback,
  getScript,
  getScripts,
  type RehearsalFeedback as RehearsalFeedbackRecord,
  type ScriptAnalysis,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const TODAY = new Date().toISOString().slice(0, 10);

const ENGINE_LABELS: Record<RehearsalFeedbackRecord["engine"], string> = {
  rules: "本地规则",
  llm: "LLM 镜像",
  fallback: "规则降级",
};

function splitParticipants(value: string): string[] {
  return Array.from(new Set(value.split(/[\n,，、]/).map((item) => item.trim()).filter(Boolean)));
}

function splitLines(value: string): string[] {
  return Array.from(new Set(value.split(/\r?\n/).map((item) => item.replace(/^[\s\-*•\d.、)）]+/, "").trim()).filter(Boolean)));
}

export default function RehearsalFeedback() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [sceneId, setSceneId] = useState("");
  const [rehearsalDate, setRehearsalDate] = useState(TODAY);
  const [participantsText, setParticipantsText] = useState("");
  const [outputsText, setOutputsText] = useState("");
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState<"auto" | "rules" | "llm">("auto");
  const [records, setRecords] = useState<RehearsalFeedbackRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void Promise.all([getScripts(), getRehearsalFeedback()])
      .then(([scriptItems, feedbackItems]) => {
        if (cancelled) return;
        setScripts(scriptItems);
        setRecords(feedbackItems);
        setSelectedScriptId((current) => (
          current && scriptItems.some((item) => item.script_id === current)
            ? current
            : ""
        ));
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "排练复盘数据加载失败");
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
      setAnalysis(null);
      setSceneId("");
      return;
    }
    let cancelled = false;
    void getScript(selectedScriptId)
      .then((item) => {
        if (cancelled) return;
        setAnalysis(item);
        setSceneId(item.scenes[0]?.scene_id || "");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本场次加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedScriptId]);

  async function submitFeedback() {
    if (!rehearsalDate) {
      setError("请先选择排练日期");
      return;
    }
    if (!notes.trim()) {
      setError("请填写本次排练的原始反馈");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const record = await createRehearsalFeedback({
        script_id: selectedScriptId || null,
        scene_id: selectedScriptId ? sceneId || null : null,
        rehearsal_date: rehearsalDate,
        participants: splitParticipants(participantsText),
        outputs: splitLines(outputsText),
        notes: notes.trim(),
        analysis_mode: mode,
      });
      setRecords((current) => [record, ...current.filter((item) => item.record_id !== record.record_id)]);
      setMessage("排练反馈已归档，镜子 Agent 已生成结构化复盘。");
      setNotes("");
      setOutputsText("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练反馈归档失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <NotebookPen className="text-primary" size={30} />
            排练复盘
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            把一次排练留下的事实、问题和下一步保存下来，让“镜子 Agent”帮助剧团形成连续记忆。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          镜子 Agent
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

      <div className="grid gap-4 xl:grid-cols-[minmax(340px,0.8fr)_minmax(560px,1.2fr)]">
        <Card>
          <CardContent className="p-4 md:p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <ClipboardCheck size={16} className="text-primary" />
                  新建排练记录
                </div>
                <p className="mt-1 text-xs leading-5 text-dim">
                  不关联剧本也可以先记；关联后会自动显示剧本和场次上下文。
                </p>
              </div>
              <span className="rounded-full border border-teal/25 bg-teal/8 px-2 py-0.5 text-[10px] text-teal">可独立使用</span>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Field label="排练日期">
                <Input type="date" value={rehearsalDate} onChange={(event) => setRehearsalDate(event.target.value)} />
              </Field>
              <Field label="整理方式">
                <select
                  value={mode}
                  onChange={(event) => setMode(event.target.value as "auto" | "rules" | "llm")}
                  className="flex h-9 w-full rounded-lg border border-border bg-input px-3 text-sm text-text outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                  aria-label="选择反馈整理方式"
                >
                  <option value="auto">自动：优先 LLM</option>
                  <option value="rules">本地规则</option>
                  <option value="llm">只用 LLM</option>
                </select>
              </Field>
            </div>

            <Field label="关联剧本（可选）" className="mt-3">
              <select
                value={selectedScriptId}
                onChange={(event) => setSelectedScriptId(event.target.value)}
                className="flex h-9 w-full rounded-lg border border-border bg-input px-3 text-sm text-text outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                aria-label="选择关联剧本"
              >
                <option value="">不关联剧本</option>
                {scripts.map((script) => (
                  <option key={script.script_id} value={script.script_id}>
                    {script.title} · {script.version_label}
                  </option>
                ))}
              </select>
            </Field>

            {selectedScriptId && (
              <Field label="关联场次（可选）" className="mt-3">
                <select
                  value={sceneId}
                  onChange={(event) => setSceneId(event.target.value)}
                  className="flex h-9 w-full rounded-lg border border-border bg-input px-3 text-sm text-text outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                  aria-label="选择关联场次"
                >
                  <option value="">不关联具体场次</option>
                  {analysis?.scenes.map((scene) => (
                    <option key={scene.scene_id} value={scene.scene_id}>
                      第 {scene.number} 场 · {scene.title}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <Field label="参与者" hint="逗号、顿号或换行分隔" className="mt-3">
              <Input
                value={participantsText}
                onChange={(event) => setParticipantsText(event.target.value)}
                placeholder="导演，小林，许教授"
              />
            </Field>

            <Field label="本次具体产出" hint="一行一项" className="mt-3">
              <Textarea
                value={outputsText}
                onChange={(event) => setOutputsText(event.target.value)}
                className="min-h-24 text-sm leading-6"
                placeholder={'完成第一场走位\n确定椅子和手电筒的位置\n录下了一版对词音频'}
              />
            </Field>

            <Field label="原始反馈" hint="尽量保留导演和演员的原话，Agent 只做整理" className="mt-3">
              <Textarea
                value={notes}
                onChange={(event) => {
                  setNotes(event.target.value);
                  setError("");
                }}
                className="min-h-44 text-sm leading-6"
                placeholder={'例如：\n小林第二段情绪已经比较清晰，但换位时还是会忘记看向门口。\n道具组缺少一把备用手电筒，下次排练前确认。'}
              />
            </Field>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[11px] text-dim">
                <Sparkles size={13} className="text-primary" />
                {mode === "rules" ? "不调用模型，立即整理" : "模型不可用时自动降级"}
              </div>
              <Button type="button" onClick={() => void submitFeedback()} disabled={saving || loading}>
                {saving ? <Loader2 className="animate-spin" /> : <NotebookPen size={14} />}
                归档反馈
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-[680px] overflow-hidden">
          <CardContent className="h-full p-4 md:p-5">
            <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
              <div>
                <div className="flex items-center gap-2 text-lg font-semibold">
                  <History size={19} className="text-primary" />
                  反馈档案
                </div>
                <p className="mt-1 text-xs leading-5 text-dim">每次归档都会保留原始笔记，并记录 Agent 的整理方式。</p>
              </div>
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">{records.length} 条</span>
            </div>

            {loading ? (
              <div className="flex min-h-[560px] flex-col items-center justify-center text-center">
                <Loader2 className="animate-spin text-primary" size={28} />
                <div className="mt-3 text-sm text-dim">正在读取反馈档案...</div>
              </div>
            ) : records.length === 0 ? (
              <div className="flex min-h-[560px] flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary">
                  <MessageSquareText size={29} />
                </div>
                <div className="mt-5 text-xl font-semibold">还没有排练反馈</div>
                <p className="mt-2 max-w-md text-sm leading-6 text-dim">
                  先记录一次真实排练。哪怕暂时没有剧本，也可以从参与者、产出和现场问题开始积累。
                </p>
                {scripts.length === 0 && (
                  <Button type="button" variant="outline" className="mt-5" onClick={() => navigate("/rehearsal")}>
                    去解析剧本
                    <ArrowRight size={14} />
                  </Button>
                )}
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {records.map((record) => <FeedbackCard key={record.record_id} record={record} />)}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="flex items-center justify-between gap-2 text-xs font-medium text-text">
        {label}
        {hint && <span className="font-normal text-dim">{hint}</span>}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

function FeedbackCard({ record }: { record: RehearsalFeedbackRecord }) {
  return (
    <article className="rounded-xl border border-border bg-background/40 p-4">
      <div className="flex flex-col gap-2 border-b border-border/70 pb-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {record.script_title || "独立排练记录"}
            {record.scene_title && <span className="font-normal text-dim">· {record.scene_title}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-dim">
            <span>{record.rehearsal_date}</span>
            <span className="inline-flex items-center gap-1"><Users size={12} /> {record.participants.length ? record.participants.join("、") : "未填写参与者"}</span>
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[10px] text-primary">
          {ENGINE_LABELS[record.engine]}
        </span>
      </div>

      <div className="mt-3 rounded-lg bg-primary/8 px-3 py-2.5 text-sm leading-6 text-text">
        <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-primary">镜像总结</div>
        {record.summary}
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <InsightList title="已形成" items={record.strengths} tone="green" empty="暂未识别明确亮点" />
        <InsightList title="待解决" items={record.blockers} tone="red" empty="暂未识别阻塞项" />
        <InsightList title="下一步" items={record.next_actions} tone="orange" empty="等待下一次复盘补充" />
      </div>

      {record.outputs.length > 0 && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-border bg-card/60 px-3 py-2.5 text-xs leading-5 text-dim">
          <FileText size={14} className="mt-0.5 shrink-0 text-teal" />
          <span><span className="text-text">具体产出：</span>{record.outputs.join("；")}</span>
        </div>
      )}

      <details className="mt-3 text-xs text-dim">
        <summary className="cursor-pointer select-none hover:text-text">查看原始反馈</summary>
        <p className="mt-2 whitespace-pre-wrap rounded-lg bg-card/60 px-3 py-2.5 leading-6">{record.notes}</p>
      </details>
    </article>
  );
}

function InsightList({
  title,
  items,
  tone,
  empty,
}: {
  title: string;
  items: string[];
  tone: "green" | "red" | "orange";
  empty: string;
}) {
  const styles = {
    green: "text-green bg-green/6",
    red: "text-red bg-red/6",
    orange: "text-orange bg-orange/6",
  };
  return (
    <div className={cn("rounded-lg px-3 py-2.5", styles[tone])}>
      <div className="text-[10px] font-medium uppercase tracking-[0.14em]">{title}</div>
      {items.length > 0 ? (
        <ul className="mt-1.5 space-y-1 text-xs leading-5 text-text">
          {items.map((item) => <li key={item}>· {item}</li>)}
        </ul>
      ) : (
        <div className="mt-1.5 text-xs leading-5 text-dim">{empty}</div>
      )}
    </div>
  );
}
