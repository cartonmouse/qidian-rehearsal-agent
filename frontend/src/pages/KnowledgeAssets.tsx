import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  BookMarked,
  Check,
  CheckCircle2,
  Copy,
  FileText,
  Heart,
  Loader2,
  Megaphone,
  Sparkles,
  Trash2,
} from "lucide-react";

import {
  createMotto,
  deleteMotto,
  generatePromoCopy,
  getMottos,
  getPromoCopies,
  getScript,
  getScripts,
  updateMotto,
  type Motto,
  type PromoCopy,
  type ScriptAnalysis,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const INPUT_CLASS = "mt-1.5 h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const THEME_LABELS: Record<Motto["theme"], string> = {
  performance: "表演",
  team: "协作",
  theatre: "戏剧",
  life: "生活",
  other: "其他",
};

const ENGINE_LABELS: Record<PromoCopy["engine"], string> = {
  rules: "本地规则",
  llm: "LLM",
  fallback: "规则降级",
};

export default function KnowledgeAssets() {
  const [mottos, setMottos] = useState<Motto[]>([]);
  const [promoCopies, setPromoCopies] = useState<PromoCopy[]>([]);
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [scriptId, setScriptId] = useState("");
  const [mottoForm, setMottoForm] = useState({
    text: "",
    author: "奇点剧团",
    source: "排练现场",
    theme: "other" as Motto["theme"],
    tags: "",
    sceneId: "",
  });
  const [promoForm, setPromoForm] = useState({
    work_title: "奇点剧团新作",
    audience: "audience" as PromoCopy["audience"],
    tone: "poetic" as PromoCopy["tone"],
    brief: "",
    analysis_mode: "auto" as "auto" | "rules" | "llm",
  });
  const [latestPromo, setLatestPromo] = useState<PromoCopy | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingMotto, setSavingMotto] = useState(false);
  const [generatingPromo, setGeneratingPromo] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    void Promise.all([getMottos(), getPromoCopies(), getScripts()])
      .then(([mottoItems, promoItems, scriptItems]) => {
        if (cancelled) return;
        setMottos(mottoItems);
        setPromoCopies(promoItems);
        setScripts(scriptItems);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "知识资产加载失败");
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
      setMottoForm((current) => ({ ...current, sceneId: "" }));
      return;
    }
    let cancelled = false;
    void getScript(scriptId)
      .then((item) => {
        if (cancelled) return;
        setAnalysis(item);
        setMottoForm((current) => ({ ...current, sceneId: "" }));
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本详情加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [scriptId]);

  async function submitMotto(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mottoForm.text.trim()) {
      setError("请先填写格言内容。");
      return;
    }
    setSavingMotto(true);
    setError("");
    setMessage("");
    try {
      const motto = await createMotto({
        script_id: scriptId || null,
        scene_id: mottoForm.sceneId || null,
        text: mottoForm.text,
        author: mottoForm.author,
        source: mottoForm.source,
        theme: mottoForm.theme,
        tags: mottoForm.tags.split(/[，,、]/).map((tag) => tag.trim()).filter(Boolean),
      });
      setMottos((items) => [motto, ...items]);
      setMottoForm((current) => ({ ...current, text: "", tags: "" }));
      setMessage("格言已保存到剧团资产库。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "格言保存失败");
    } finally {
      setSavingMotto(false);
    }
  }

  async function toggleFavorite(motto: Motto) {
    try {
      const updated = await updateMotto(motto.motto_id, !motto.favorite);
      setMottos((items) => items.map((item) => item.motto_id === updated.motto_id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "格言收藏状态更新失败");
    }
  }

  async function removeMotto(mottoId: string) {
    try {
      await deleteMotto(mottoId);
      setMottos((items) => items.filter((item) => item.motto_id !== mottoId));
      setMessage("格言已删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "格言删除失败");
    }
  }

  async function generatePromo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!promoForm.work_title.trim()) {
      setError("请先填写作品名称。");
      return;
    }
    setGeneratingPromo(true);
    setError("");
    setMessage("");
    try {
      const copy = await generatePromoCopy({
        script_id: scriptId || null,
        work_title: promoForm.work_title,
        audience: promoForm.audience,
        tone: promoForm.tone,
        brief: promoForm.brief,
        analysis_mode: promoForm.analysis_mode,
      });
      setLatestPromo(copy);
      setPromoCopies((items) => [copy, ...items]);
      setMessage(`宣传文案已生成（${ENGINE_LABELS[copy.engine]}）。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "宣传文案生成失败");
    } finally {
      setGeneratingPromo(false);
    }
  }

  async function copyText(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage("文案已复制到剪贴板。");
    } catch {
      setError("当前浏览器不允许自动复制，请手动选择文案。");
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]"><BookMarked className="text-primary" size={30} />知识资产</div>
          <p className="mt-1 text-sm leading-6 text-dim">把排练中值得留下的话和对外表达，沉淀成剧团可以继续使用的资产。</p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">Knowledge Agents</div>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green"><CheckCircle2 size={16} />{message}</div>}

      <Card><CardContent className="p-4 md:p-5"><div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><div className="flex items-center gap-2 text-sm font-semibold"><FileText size={16} className="text-primary" />共享上下文</div><p className="mt-1 text-xs leading-5 text-dim">选择剧本后，格言和宣传文案都可以自动带上剧本、场次标题与角色信息；两项功能也都可以独立使用。</p></div><label className="w-full md:max-w-sm"><span className="text-[11px] font-medium text-text">当前剧本版本</span><select value={scriptId} onChange={(event) => setScriptId(event.target.value)} className={INPUT_CLASS} aria-label="选择知识资产剧本"><option value="">不关联剧本</option>{scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label}</option>)}</select></label></div></CardContent></Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.72fr)_minmax(560px,1.28fr)]">
        <Card><CardContent className="p-4 md:p-5"><div className="flex items-start gap-3 border-b border-border pb-4"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"><BookMarked size={18} /></div><div><div className="text-sm font-semibold">格言表</div><p className="mt-1 text-xs leading-5 text-dim">保存剧团成员认为值得带回排练场的话，不自动改写原文。</p></div></div><form className="mt-4 space-y-3" onSubmit={submitMotto}><Field label="格言内容"><Textarea value={mottoForm.text} onChange={(event) => setMottoForm((current) => ({ ...current, text: event.target.value }))} className="mt-1.5 min-h-28 leading-6" placeholder="例如：先让角色抵达，再让台词发生。" required /></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="作者 / 说话人"><input value={mottoForm.author} onChange={(event) => setMottoForm((current) => ({ ...current, author: event.target.value }))} className={INPUT_CLASS} required /></Field><Field label="主题"><select value={mottoForm.theme} onChange={(event) => setMottoForm((current) => ({ ...current, theme: event.target.value as Motto["theme"] }))} className={INPUT_CLASS}><option value="performance">表演</option><option value="team">协作</option><option value="theatre">戏剧</option><option value="life">生活</option><option value="other">其他</option></select></Field></div><div className="grid gap-3 sm:grid-cols-2"><Field label="来源"><input value={mottoForm.source} onChange={(event) => setMottoForm((current) => ({ ...current, source: event.target.value }))} className={INPUT_CLASS} /></Field><Field label="标签"><input value={mottoForm.tags} onChange={(event) => setMottoForm((current) => ({ ...current, tags: event.target.value }))} className={INPUT_CLASS} placeholder="节奏，呼吸（逗号分隔）" /></Field></div><Field label="关联场次（可选）"><select value={mottoForm.sceneId} onChange={(event) => setMottoForm((current) => ({ ...current, sceneId: event.target.value }))} className={INPUT_CLASS} disabled={!analysis}><option value="">不关联具体场次</option>{analysis?.scenes.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>第 {scene.number} 场 · {scene.title}</option>)}</select></Field><Button type="submit" className="w-full" disabled={savingMotto}>{savingMotto ? <Loader2 className="animate-spin" /> : <BookMarked size={14} />}{savingMotto ? "正在保存" : "保存格言"}</Button></form><div className="mt-5 border-t border-border pt-4"><div className="flex items-center justify-between text-xs font-semibold"><span>已保存格言</span><span className="text-dim">{mottos.length} 条</span></div>{loading ? <div className="mt-3 h-20 animate-pulse rounded-xl bg-hover" /> : mottos.length === 0 ? <div className="mt-3 rounded-xl border border-dashed border-border px-3 py-5 text-center text-xs text-dim">还没有格言，先保存一句排练现场的话。</div> : <div className="mt-3 max-h-[470px] space-y-2 overflow-y-auto pr-1">{mottos.map((motto) => <MottoCard key={motto.motto_id} motto={motto} onToggle={() => void toggleFavorite(motto)} onDelete={() => void removeMotto(motto.motto_id)} />)}</div>}</div></CardContent></Card>

        <Card><CardContent className="p-4 md:p-5"><div className="flex items-start gap-3 border-b border-border pb-4"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"><Megaphone size={18} /></div><div><div className="text-sm font-semibold">宣传文案 Agent</div><p className="mt-1 text-xs leading-5 text-dim">根据已保存的剧本结构生成标题、短文案、长文案和标签；无 LLM 时自动使用本地规则。</p></div></div><form className="mt-4 space-y-3" onSubmit={generatePromo}><div className="grid gap-3 md:grid-cols-2"><Field label="作品名称"><input value={promoForm.work_title} onChange={(event) => setPromoForm((current) => ({ ...current, work_title: event.target.value }))} className={INPUT_CLASS} required /></Field><Field label="目标用途"><select value={promoForm.audience} onChange={(event) => setPromoForm((current) => ({ ...current, audience: event.target.value as PromoCopy["audience"] }))} className={INPUT_CLASS}><option value="audience">面向观众</option><option value="recruitment">招募伙伴</option><option value="media">媒体动态</option><option value="festival">节展介绍</option></select></Field><Field label="语气"><select value={promoForm.tone} onChange={(event) => setPromoForm((current) => ({ ...current, tone: event.target.value as PromoCopy["tone"] }))} className={INPUT_CLASS}><option value="poetic">诗性</option><option value="concise">简洁</option><option value="warm">温暖</option><option value="experimental">实验性</option></select></Field><Field label="生成模式"><select value={promoForm.analysis_mode} onChange={(event) => setPromoForm((current) => ({ ...current, analysis_mode: event.target.value as "auto" | "rules" | "llm" }))} className={INPUT_CLASS}><option value="auto">自动（推荐）</option><option value="rules">本地规则</option><option value="llm">仅 LLM</option></select></Field></div><Field label="宣传 brief（可选）"><Textarea value={promoForm.brief} onChange={(event) => setPromoForm((current) => ({ ...current, brief: event.target.value }))} className="mt-1.5 min-h-24 leading-6" placeholder="例如：突出排练中的身体关系，不要透露剧情结局。" /></Field><Button type="submit" className="w-full" disabled={generatingPromo}>{generatingPromo ? <Loader2 className="animate-spin" /> : <Sparkles size={14} />}{generatingPromo ? "正在生成" : "生成宣传文案"}</Button></form>{latestPromo ? <PromoResult copy={latestPromo} onCopy={(value) => void copyText(value)} /> : <div className="mt-4 rounded-xl border border-dashed border-border bg-background/35 px-4 py-8 text-center text-sm leading-6 text-dim">生成结果会在这里展示，规则分支不会等待 API Key。</div>}<div className="mt-5 border-t border-border pt-4"><div className="flex items-center justify-between text-xs font-semibold"><span>历史文案</span><span className="text-dim">{promoCopies.length} 条</span></div>{promoCopies.length > 0 && <div className="mt-3 max-h-64 space-y-2 overflow-y-auto pr-1">{promoCopies.map((copy) => <button type="button" key={copy.copy_id} className="block w-full rounded-xl border border-border bg-background/35 px-3 py-2.5 text-left transition-colors hover:border-primary/30" onClick={() => setLatestPromo(copy)}><div className="flex items-center justify-between gap-2"><span className="truncate text-xs font-medium text-text">{copy.headline}</span><span className="shrink-0 rounded-full bg-hover px-2 py-0.5 text-[10px] text-dim">{ENGINE_LABELS[copy.engine]}</span></div><div className="mt-1 text-[11px] text-dim">{new Date(copy.created_at).toLocaleString("zh-CN")}</div></button>)}</div>}</div></CardContent></Card>
      </div>
    </div>
  );
}

function MottoCard({ motto, onToggle, onDelete }: { motto: Motto; onToggle: () => void; onDelete: () => void }) {
  return <article className="rounded-xl border border-border bg-background/35 p-3"><div className="flex items-start justify-between gap-2"><div className="flex flex-wrap items-center gap-1.5 text-[10px]"><span className="rounded-full bg-primary/10 px-2 py-0.5 text-primary">{THEME_LABELS[motto.theme]}</span>{motto.script_title && <span className="rounded-full bg-teal/10 px-2 py-0.5 text-teal">{motto.script_title}{motto.scene_title ? ` · ${motto.scene_title}` : ""}</span>}</div><div className="flex shrink-0 gap-2"><button type="button" className={cn("transition-colors", motto.favorite ? "text-red" : "text-dim hover:text-red")} onClick={onToggle} aria-label={motto.favorite ? "取消收藏格言" : "收藏格言"}><Heart size={15} fill={motto.favorite ? "currentColor" : "none"} /></button><button type="button" className="text-dim transition-colors hover:text-red" onClick={onDelete} aria-label="删除格言"><Trash2 size={15} /></button></div></div><div className="mt-2 text-sm leading-6 text-text">“{motto.text}”</div><div className="mt-2 text-[11px] text-dim">—— {motto.author} · {motto.source}</div>{motto.tags.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{motto.tags.map((tag) => <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-[10px] text-dim">{tag}</span>)}</div>}</article>;
}

function PromoResult({ copy, onCopy }: { copy: PromoCopy; onCopy: (value: string) => void }) {
  return <div className="mt-4 space-y-3"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2 text-xs font-semibold"><Sparkles size={15} className="text-primary" />生成结果<span className="rounded-full bg-teal/10 px-2 py-0.5 text-[10px] font-normal text-teal">{ENGINE_LABELS[copy.engine]}</span></div><button type="button" className="inline-flex items-center gap-1 text-[11px] text-dim hover:text-primary" onClick={() => onCopy(`${copy.headline}\n\n${copy.short_copy}\n\n${copy.long_copy}\n\n${copy.hashtags.join(" ")}`)}><Copy size={13} />复制全部</button></div><div className="rounded-xl border border-primary/20 bg-primary/6 p-4"><div className="text-lg font-semibold leading-7 text-text">{copy.headline}</div><div className="mt-3 text-sm leading-6 text-text">{copy.short_copy}</div><div className="mt-3 border-t border-border/70 pt-3 text-xs leading-6 text-dim">{copy.long_copy}</div><div className="mt-3 flex flex-wrap gap-1.5">{copy.hashtags.map((tag) => <span key={tag} className="rounded-full bg-hover px-2 py-0.5 text-[10px] text-primary">{tag}</span>)}</div></div><div className="flex items-start gap-2 rounded-xl border border-border bg-background/35 px-3 py-2.5 text-[11px] leading-5 text-dim"><Check size={13} className="mt-0.5 shrink-0 text-teal" />{copy.note}</div></div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block min-w-0"><span className="text-[11px] font-medium text-text">{label}</span>{children}</label>;
}
