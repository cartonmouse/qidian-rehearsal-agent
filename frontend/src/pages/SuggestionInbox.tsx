import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Flag,
  Inbox,
  Loader2,
  MessageSquareText,
  Send,
  Trash2,
} from "lucide-react";

import {
  createSuggestion,
  deleteSuggestion,
  getScript,
  getScripts,
  getSuggestions,
  updateSuggestion,
  type ScriptAnalysis,
  type ScriptSummary,
  type Suggestion,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const INPUT_CLASS = "mt-1.5 h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const CATEGORY_LABELS: Record<Suggestion["category"], string> = {
  performance: "表演",
  blocking: "走位",
  script: "剧本",
  team: "协作",
  safety: "安全",
  other: "其他",
};

const STATUS_LABELS: Record<Suggestion["status"], string> = {
  new: "待处理",
  reviewed: "已阅",
  accepted: "已采纳",
  archived: "已归档",
};

export default function SuggestionInbox() {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [scriptId, setScriptId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [form, setForm] = useState({ actor_name: "", category: "other" as Suggestion["category"], content: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getSuggestions(), getScripts()])
      .then(([suggestionItems, scriptItems]) => {
        if (cancelled) return;
        setSuggestions(suggestionItems);
        setScripts(scriptItems);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "建议收件箱加载失败");
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
        setSceneId("");
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
    if (!form.actor_name.trim() || !form.content.trim()) {
      setError("请填写演员姓名和建议内容。");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const suggestion = await createSuggestion({
        script_id: scriptId || null,
        scene_id: sceneId || null,
        actor_name: form.actor_name,
        category: form.category,
        content: form.content,
      });
      setSuggestions((items) => [suggestion, ...items]);
      setForm((current) => ({ ...current, content: "" }));
      setMessage("建议已送入收件箱，原始内容已保留。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建议提交失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(suggestionId: string) {
    setError("");
    try {
      await deleteSuggestion(suggestionId);
      setSuggestions((items) => items.filter((item) => item.suggestion_id !== suggestionId));
      setMessage("建议已删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建议删除失败");
    }
  }

  async function handleUpdate(suggestion: Suggestion, status: Suggestion["status"], response: string) {
    setError("");
    try {
      const updated = await updateSuggestion(suggestion.suggestion_id, { status, response });
      setSuggestions((items) => items.map((item) => item.suggestion_id === updated.suggestion_id ? updated : item));
      setMessage("建议处理状态已保存。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建议状态更新失败");
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]"><Inbox className="text-primary" size={30} />建议收件箱</div>
          <p className="mt-1 text-sm leading-6 text-dim">让演员可以安全留下建议，让导演能看见、回应并把有价值的意见沉淀进排练流程。</p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">Suggestion Agent</div>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green"><CheckCircle2 size={16} />{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.7fr)_minmax(560px,1.3fr)]">
        <Card>
          <CardContent className="p-4 md:p-5">
            <div className="flex items-start gap-3 border-b border-border pb-4"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"><Send size={18} /></div><div><div className="text-sm font-semibold">提交一条建议</div><p className="mt-1 text-xs leading-5 text-dim">安全、受伤、设备故障等明确风险会自动标记为高优先级。</p></div></div>
            <form className="mt-4 space-y-3" onSubmit={submit}>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="演员姓名"><input value={form.actor_name} onChange={(event) => setForm((current) => ({ ...current, actor_name: event.target.value }))} className={INPUT_CLASS} placeholder="例如：小林" required /></Field>
                <Field label="建议类型"><select value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value as Suggestion["category"] }))} className={INPUT_CLASS}><option value="performance">表演</option><option value="blocking">走位</option><option value="script">剧本</option><option value="team">协作</option><option value="safety">安全</option><option value="other">其他</option></select></Field>
              </div>
              <Field label="关联剧本（可选）"><select value={scriptId} onChange={(event) => setScriptId(event.target.value)} className={INPUT_CLASS}><option value="">不关联剧本</option>{scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label}</option>)}</select></Field>
              <Field label="关联场次（可选）"><select value={sceneId} onChange={(event) => setSceneId(event.target.value)} className={INPUT_CLASS} disabled={!analysis}><option value="">不关联具体场次</option>{analysis?.scenes.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>第 {scene.number} 场 · {scene.title}</option>)}</select></Field>
              <label className="block"><span className="text-[11px] font-medium text-text">建议内容</span><Textarea value={form.content} onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))} className="mt-1.5 min-h-44 leading-6" placeholder="例如：第二场的换位可以提前半拍，否则演员会在台口互相遮挡。" required /></label>
              <Button type="submit" className="w-full" disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <Send size={14} />}{saving ? "正在提交" : "提交建议"}</Button>
            </form>
          </CardContent>
        </Card>

        <Card className="min-h-[680px]"><CardContent className="p-4 md:p-5"><div className="flex items-start justify-between gap-3 border-b border-border pb-4"><div><div className="flex items-center gap-2 text-sm font-semibold"><MessageSquareText size={16} className="text-primary" />全部建议</div><p className="mt-1 text-xs leading-5 text-dim">每条建议保留提交人、原文、上下文和处理回应。</p></div><span className="rounded-full bg-primary/10 px-2.5 py-1 text-[10px] text-primary">{suggestions.length} 条</span></div>{loading ? <div className="mt-4 space-y-3"><div className="h-32 animate-pulse rounded-xl bg-hover" /><div className="h-32 animate-pulse rounded-xl bg-hover" /></div> : suggestions.length === 0 ? <EmptyInbox /> : <div className="mt-4 space-y-3">{suggestions.map((suggestion) => <SuggestionCard key={suggestion.suggestion_id} suggestion={suggestion} onUpdate={handleUpdate} onDelete={() => void handleDelete(suggestion.suggestion_id)} />)}</div>}</CardContent></Card>
      </div>
    </div>
  );
}

function SuggestionCard({ suggestion, onUpdate, onDelete }: { suggestion: Suggestion; onUpdate: (suggestion: Suggestion, status: Suggestion["status"], response: string) => Promise<void>; onDelete: () => void }) {
  const [status, setStatus] = useState(suggestion.status);
  const [response, setResponse] = useState(suggestion.response);
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await onUpdate(suggestion, status, response);
    } finally {
      setSaving(false);
    }
  }
  return <article className="rounded-xl border border-border bg-background/35 p-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"><div className="flex flex-wrap items-center gap-1.5 text-[11px]"><span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">{CATEGORY_LABELS[suggestion.category]}</span><span className={cn("rounded-full px-2.5 py-1", suggestion.priority === "high" ? "bg-red/10 text-red" : "bg-hover text-dim")}>{suggestion.priority === "high" ? <><Flag size={11} className="mr-1 inline" />高优先级</> : "普通"}</span><span className="rounded-full bg-hover px-2.5 py-1 text-dim">{suggestion.actor_name}</span>{suggestion.script_title && <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{suggestion.script_title}{suggestion.scene_title ? ` · ${suggestion.scene_title}` : ""}</span>}</div><button type="button" className="self-end text-dim transition-colors hover:text-red sm:self-auto" onClick={onDelete} aria-label="删除建议"><Trash2 size={15} /></button></div><div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-text">{suggestion.content}</div><div className="mt-4 grid gap-2 md:grid-cols-[0.35fr_1fr_auto] md:items-end"><Field label="处理状态"><select value={status} onChange={(event) => setStatus(event.target.value as Suggestion["status"])} className={INPUT_CLASS}><option value="new">待处理</option><option value="reviewed">已阅</option><option value="accepted">已采纳</option><option value="archived">已归档</option></select></Field><Field label="导演回应"><input value={response} onChange={(event) => setResponse(event.target.value)} className={INPUT_CLASS} placeholder="可选：说明处理决定" /></Field><Button type="button" size="sm" onClick={() => void save()} disabled={saving}>{saving ? <Loader2 className="animate-spin" /> : <CheckCircle2 size={14} />}保存处理</Button></div><div className="mt-2 text-[11px] text-dim">当前状态：{STATUS_LABELS[status]} · 提交于 {new Date(suggestion.created_at).toLocaleString("zh-CN")}</div></article>;
}

function EmptyInbox() {
  return <div className="flex min-h-[540px] flex-col items-center justify-center text-center"><div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary"><Inbox size={29} /></div><div className="mt-5 text-xl font-semibold">收件箱还是空的</div><p className="mt-2 max-w-md text-sm leading-6 text-dim">第一条建议可以来自演员对走位、表演、剧本或排练协作的真实观察。</p></div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block min-w-0"><span className="text-[11px] font-medium text-text">{label}</span>{children}</label>;
}
