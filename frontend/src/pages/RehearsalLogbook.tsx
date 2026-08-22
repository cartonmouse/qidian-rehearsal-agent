import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ClipboardPenLine,
  FileText,
  Loader2,
  Tag,
  Trash2,
} from "lucide-react";

import {
  createRehearsalLog,
  deleteRehearsalLog,
  getRehearsalLogs,
  getScript,
  getScripts,
  type RehearsalLog,
  type ScriptAnalysis,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const INPUT_CLASS = "mt-1.5 h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const CATEGORY_LABELS: Record<RehearsalLog["category"], string> = {
  direction: "导演指令",
  actor: "演员状态",
  blocking: "走位",
  prop: "道具",
  sound: "声音 / 配乐",
  general: "一般记录",
};

const CATEGORY_COLORS: Record<RehearsalLog["category"], string> = {
  direction: "bg-primary/10 text-primary",
  actor: "bg-teal/10 text-teal",
  blocking: "bg-orange/10 text-orange",
  prop: "bg-blue/10 text-blue-300",
  sound: "bg-accent/10 text-accent-light",
  general: "bg-hover text-dim",
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function RehearsalLogbook() {
  const [logs, setLogs] = useState<RehearsalLog[]>([]);
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [scriptId, setScriptId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [form, setForm] = useState({
    rehearsal_date: today(),
    author: "场记",
    category: "general" as RehearsalLog["category"],
    content: "",
    tags: "",
    source_line: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getRehearsalLogs(), getScripts()])
      .then(([logItems, scriptItems]) => {
        if (cancelled) return;
        setLogs(logItems);
        setScripts(scriptItems);
        setScriptId((current) => current && scriptItems.some((item) => item.script_id === current) ? current : "");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "场记数据加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!scriptId) {
      setAnalysis(null);
      setSceneId("");
      return;
    }
    let cancelled = false;
    void getScript(scriptId)
      .then((item) => {
        if (cancelled) return;
        setAnalysis(item);
        setSceneId((current) => item.scenes.some((scene) => scene.scene_id === current) ? current : "");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本详情加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [scriptId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.content.trim()) {
      setError("请先写下本次排练的现场记录。");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const record = await createRehearsalLog({
        script_id: scriptId || null,
        scene_id: sceneId || null,
        rehearsal_date: form.rehearsal_date,
        author: form.author,
        category: form.category,
        content: form.content,
        tags: form.tags.split(/[，,、]/).map((tag) => tag.trim()).filter(Boolean),
        source_line: form.source_line.trim() ? Number(form.source_line) : null,
      });
      setLogs((items) => [record, ...items]);
      setForm((current) => ({ ...current, content: "", tags: "", source_line: "" }));
      setMessage("场记已归档，原始内容和关联证据均已保留。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "场记归档失败");
    } finally {
      setSaving(false);
    }
  }

  async function remove(logId: string) {
    setError("");
    try {
      await deleteRehearsalLog(logId);
      setLogs((items) => items.filter((item) => item.log_id !== logId));
      setMessage("场记记录已删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "场记删除失败");
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <ClipboardPenLine className="text-primary" size={30} />
            场记档案
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">记录导演、演员和场面调度的现场变化，让每次排练都能留下可回看的知识资产。</p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">Logbook Agent</div>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green"><CheckCircle2 size={16} />{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.72fr)_minmax(560px,1.28fr)]">
        <Card>
          <CardContent className="p-4 md:p-5">
            <div className="flex items-start gap-3 border-b border-border pb-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"><BookOpen size={19} /></div>
              <div><div className="text-sm font-semibold">新增现场记录</div><p className="mt-1 text-xs leading-5 text-dim">原文只保存不改写；分类和标签帮助之后检索。</p></div>
            </div>
            <form className="mt-4 space-y-3" onSubmit={submit}>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="排练日期"><input type="date" value={form.rehearsal_date} onChange={(event) => setForm((current) => ({ ...current, rehearsal_date: event.target.value }))} className={INPUT_CLASS} required /></Field>
                <Field label="记录人"><input value={form.author} onChange={(event) => setForm((current) => ({ ...current, author: event.target.value }))} className={INPUT_CLASS} required /></Field>
                <Field label="记录类型"><select value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value as RehearsalLog["category"] }))} className={INPUT_CLASS}><option value="general">一般记录</option><option value="direction">导演指令</option><option value="actor">演员状态</option><option value="blocking">走位</option><option value="prop">道具</option><option value="sound">声音 / 配乐</option></select></Field>
                <Field label="原文行号（可选）"><input type="number" min={1} value={form.source_line} onChange={(event) => setForm((current) => ({ ...current, source_line: event.target.value }))} className={INPUT_CLASS} placeholder="例如：28" /></Field>
              </div>
              <Field label="关联剧本（可选）"><select value={scriptId} onChange={(event) => { setScriptId(event.target.value); setSceneId(""); }} className={INPUT_CLASS}><option value="">不关联剧本</option>{scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label}</option>)}</select></Field>
              <Field label="关联场次（可选）"><select value={sceneId} onChange={(event) => setSceneId(event.target.value)} className={INPUT_CLASS} disabled={!analysis}><option value="">不关联具体场次</option>{analysis?.scenes.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>第 {scene.number} 场 · {scene.title}</option>)}</select></Field>
              <Field label="标签"><input value={form.tags} onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))} className={INPUT_CLASS} placeholder="情绪，节奏，待确认（逗号分隔）" /></Field>
              <label className="block"><span className="text-[11px] font-medium text-text">现场原话 / 观察</span><Textarea value={form.content} onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))} className="mt-1.5 min-h-44 leading-6" placeholder="例如：第二次走位时，小林从台口回到中央的停顿更自然，但拿椅子时仍会挡住许教授。" required /></label>
              <Button type="submit" className="w-full" disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <ClipboardPenLine size={14} />}{saving ? "正在归档" : "保存场记"}</Button>
            </form>
          </CardContent>
        </Card>

        <Card className="min-h-[680px]">
          <CardContent className="p-4 md:p-5">
            <div className="flex items-start justify-between gap-3 border-b border-border pb-4"><div><div className="flex items-center gap-2 text-sm font-semibold"><FileText size={16} className="text-primary" />历史场记</div><p className="mt-1 text-xs leading-5 text-dim">按创建时间倒序展示，记录可回看关联剧本和场次。</p></div><span className="rounded-full bg-primary/10 px-2.5 py-1 text-[10px] text-primary">{logs.length} 条</span></div>
            {loading ? <div className="mt-4 space-y-3"><div className="h-28 animate-pulse rounded-xl bg-hover" /><div className="h-28 animate-pulse rounded-xl bg-hover" /></div> : logs.length === 0 ? <div className="flex min-h-[540px] flex-col items-center justify-center text-center"><div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary"><ClipboardPenLine size={29} /></div><div className="mt-5 text-xl font-semibold">还没有场记记录</div><p className="mt-2 max-w-md text-sm leading-6 text-dim">把一次排练中的具体观察写下来，之后可以按剧本、场次和标签继续沉淀。</p></div> : <div className="mt-4 space-y-3">{logs.map((log) => <LogCard key={log.log_id} log={log} onRemove={() => void remove(log.log_id)} />)}</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LogCard({ log, onRemove }: { log: RehearsalLog; onRemove: () => void }) {
  return <article className="rounded-xl border border-border bg-background/35 p-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"><div className="flex flex-wrap items-center gap-1.5 text-[11px]"><span className={cn("rounded-full px-2.5 py-1", CATEGORY_COLORS[log.category])}>{CATEGORY_LABELS[log.category]}</span><span className="rounded-full bg-hover px-2.5 py-1 text-dim">{log.rehearsal_date}</span>{log.script_title && <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{log.script_title}{log.scene_title ? ` · ${log.scene_title}` : ""}</span>}</div><button type="button" className="self-end text-dim transition-colors hover:text-red sm:self-auto" onClick={onRemove} aria-label="删除场记"><Trash2 size={15} /></button></div><div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-text">{log.content}</div><div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-dim"><span>记录人：{log.author}</span>{log.source_line && <span>原文第 {log.source_line} 行</span>}{log.tags.map((tag) => <span key={tag} className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5"><Tag size={11} />{tag}</span>)}</div></article>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block min-w-0"><span className="text-[11px] font-medium text-text">{label}</span>{children}</label>;
}
