import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileSearch,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";

import {
  askScriptRag,
  getScripts,
  type ScriptRagResponse,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";
const SELECT_CLASS = "flex h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/30";

const ENGINE_LABELS: Record<ScriptRagResponse["engine"], string> = {
  rules: "本地规则",
  llm: "LLM 组织",
  fallback: "LLM 降级",
};

const RETRIEVAL_LABELS: Record<ScriptRagResponse["retrieval_engine"], string> = {
  rules: "关键词检索",
  semantic: "语义检索",
  "rules-fallback": "规则降级",
};

export default function ScriptRag() {
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [scriptId, setScriptId] = useState("");
  const [question, setQuestion] = useState("");
  const [retrievalMode, setRetrievalMode] = useState<"rules" | "semantic">("rules");
  const [answerMode, setAnswerMode] = useState<"auto" | "rules" | "llm">("auto");
  const [topK, setTopK] = useState("5");
  const [result, setResult] = useState<ScriptRagResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    void getScripts()
      .then((items) => {
        if (cancelled) return;
        setScripts(items);
        setScriptId((current) => current || items[0]?.script_id || "");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本列表加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scriptId) {
      setError("请先选择一个已保存的剧本版本。");
      return;
    }
    if (!question.trim()) {
      setError("请先输入一个剧本问题。");
      return;
    }
    setAsking(true);
    setError("");
    setMessage("");
    try {
      const response = await askScriptRag(scriptId, {
        question: question.trim(),
        top_k: Number(topK),
        retrieval_mode: retrievalMode,
        answer_mode: answerMode,
      });
      setResult(response);
      setMessage(`已返回 ${response.evidence.length} 条可核对证据。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "剧本问答失败");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Search className="text-primary" size={30} />
            剧本问答
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            先检索剧本原文，再组织回答；每条结果都能回到场次和原文行号。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          Evidence-grounded RAG
        </div>
      </header>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green"><CheckCircle2 size={16} />{message}</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.72fr)_minmax(560px,1.28fr)]">
        <Card>
          <CardContent className="p-4 md:p-5">
            <div className="flex items-start gap-3 border-b border-border pb-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"><FileSearch size={18} /></div>
              <div>
                <div className="text-sm font-semibold">向剧本提问</div>
                <p className="mt-1 text-xs leading-5 text-dim">只回答当前选中的剧本版本，不把其他用户或其他剧本混入上下文。</p>
              </div>
            </div>

            <form className="mt-4 space-y-3" onSubmit={submitQuestion}>
              <Field label="剧本版本">
                <select value={scriptId} onChange={(event) => setScriptId(event.target.value)} className={SELECT_CLASS} aria-label="选择剧本版本" disabled={loading}>
                  <option value="">{loading ? "正在加载剧本" : "请选择剧本"}</option>
                  {scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label} · {script.review_status}</option>)}
                </select>
              </Field>

              <Field label="问题">
                <Textarea value={question} onChange={(event) => setQuestion(event.target.value)} className="mt-1.5 min-h-32 leading-6" placeholder="例如：第一场小林拿起了什么？许教授在哪一场带着手电筒上场？" required />
              </Field>

              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="检索方式">
                  <select value={retrievalMode} onChange={(event) => setRetrievalMode(event.target.value as "rules" | "semantic")} className={SELECT_CLASS} aria-label="选择检索方式">
                    <option value="rules">规则检索</option>
                    <option value="semantic">语义检索</option>
                  </select>
                </Field>
                <Field label="回答方式">
                  <select value={answerMode} onChange={(event) => setAnswerMode(event.target.value as "auto" | "rules" | "llm")} className={SELECT_CLASS} aria-label="选择回答方式">
                    <option value="auto">自动降级</option>
                    <option value="rules">只用规则</option>
                    <option value="llm">只用 LLM</option>
                  </select>
                </Field>
                <Field label="证据数量">
                  <Input type="number" min={1} max={8} value={topK} onChange={(event) => setTopK(event.target.value)} />
                </Field>
              </div>

              <div className="rounded-xl border border-primary/15 bg-primary/5 px-3 py-2.5 text-xs leading-5 text-dim">
                <div className="flex items-center gap-2 font-medium text-text"><BookOpen size={14} className="text-primary" />两阶段 Agent 流程</div>
                <div className="mt-1">检索器负责找证据，回答器只能在证据范围内组织语言；没有命中时不会让模型猜测。</div>
              </div>

              <Button type="submit" className="w-full" disabled={asking || loading || !scriptId}>
                {asking ? <Loader2 className="animate-spin" size={15} /> : <Sparkles size={15} />}
                {asking ? "正在检索并回答" : "开始剧本问答"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="min-h-[620px]">
          <CardContent className="p-4 md:p-5">
            {!result ? (
              <div className="flex min-h-[560px] flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Search size={26} /></div>
                <div className="mt-4 text-lg font-semibold">等待一次有证据的提问</div>
                <p className="mt-2 max-w-md text-sm leading-6 text-dim">例如询问某个角色在第几场出现、某件道具在哪里出现，结果会展示具体场次、原文和行号。</p>
              </div>
            ) : (
              <RagResult result={result} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function RagResult({ result }: { result: ScriptRagResponse }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles size={15} className="text-primary" />回答结果</div>
          <div className="mt-1 text-xs text-dim">{result.script_title} · {result.question}</div>
        </div>
        <div className="flex gap-1.5 text-[10px]">
          <span className="rounded-full bg-primary/10 px-2 py-1 text-primary">{ENGINE_LABELS[result.engine]}</span>
          <span className="rounded-full bg-teal/10 px-2 py-1 text-teal">{RETRIEVAL_LABELS[result.retrieval_engine]}</span>
        </div>
      </div>

      <div className="rounded-xl border border-primary/20 bg-primary/6 p-4 text-sm leading-7 text-text whitespace-pre-wrap">{result.answer}</div>

      <div>
        <div className="flex items-center justify-between text-xs font-semibold"><span>可核对证据</span><span className="text-dim">{result.evidence.length} 条</span></div>
        {result.evidence.length === 0 ? <div className="mt-3 rounded-xl border border-dashed border-border px-3 py-5 text-center text-xs text-dim">没有足够证据，回答器已停止猜测。</div> : <div className="mt-3 space-y-2">{result.evidence.map((item) => <article key={item.evidence_id} className="rounded-xl border border-border bg-background/35 p-3"><div className="flex flex-wrap items-center gap-1.5 text-[10px]"><span className="rounded-full bg-hover px-2 py-0.5 text-primary">第 {item.scene_number} 场 · {item.scene_title}</span><span className="rounded-full bg-hover px-2 py-0.5 text-dim">原文第 {item.source_line} 行</span>{item.character && <span className="rounded-full bg-hover px-2 py-0.5 text-dim">{item.character}</span>}</div><div className="mt-2 text-sm leading-6 text-text">[{item.evidence_id}] {item.text}</div><div className="mt-1 text-[10px] text-dim">{item.match_reason} · score {item.score.toFixed(2)}</div></article>)}</div>}
      </div>

      <div className="rounded-xl border border-border bg-background/35 px-3 py-2.5 text-[11px] leading-5 text-dim">{result.note}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block min-w-0"><span className="text-[11px] font-medium text-text">{label}</span><div className="mt-1.5">{children}</div></label>;
}
