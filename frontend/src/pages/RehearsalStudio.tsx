import { useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  Loader2,
  Orbit,
  Package,
  Play,
  Users,
} from "lucide-react";

import { parseScript, parseScriptFile, type ScriptAnalysis } from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

const DEMO_SCRIPT = `# 《轨道之外》排练示例

第一场 排练室·傍晚

（舞台中央放着一张椅子。小林拿起手电筒，照向门口。）

导演：所有人先不要急着走位，我们先确认第一场的节奏。

小林：我总觉得这封信不是写给我的。

许教授：信封里只有一张纸条，但它改变了我们对这条轨道的理解。

（小周把剧本放在桌上，打开手机计时。）

小周：从灯光亮起到第一次停顿，应该给观众十二秒。

第二场 天台·夜

（椅子被推到舞台右侧。许教授带着手电筒走上场。）

许教授：如果所有人都在绕着同一个问题旋转，我们要不要换一个方向？

小林：我愿意试一次，但请把这张纸条留在这里。`;

const TRACE_LABELS: Record<string, string> = {
  ingest: "摄取",
  split_scenes: "分场",
  extract_entities_parallel: "并行抽取",
  validate: "校验",
  repair: "修复",
};

export default function RehearsalStudio() {
  const [title, setTitle] = useState("轨道之外");
  const [versionLabel, setVersionLabel] = useState("v1");
  const [scriptText, setScriptText] = useState(DEMO_SCRIPT);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function analyze() {
    const value = scriptText.trim();
    if (!value) {
      setError("请先输入剧本文本");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setAnalysis(await parseScript({
        title: title.trim() || "未命名剧本",
        version_label: versionLabel.trim() || "v1",
        script_text: value,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "剧本解析失败");
    } finally {
      setBusy(false);
    }
  }

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const result = await parseScriptFile(file, versionLabel.trim() || "v1");
      setTitle(result.title);
      setScriptText(`已上传 ${file.name}，解析结果已保存。`);
      setAnalysis(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件解析失败");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Orbit className="text-primary" size={30} />
            排练中枢
          </div>
          <div className="mt-1 text-sm leading-6 text-dim">
            剧本解读 Agent：把文本变成可核对、可调度的排练结构。
          </div>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          当前节点 · 剧本解析
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.4fr)]">
        <Card className="min-h-[680px] overflow-hidden">
          <CardContent className="flex h-full flex-col gap-4 p-4 md:p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">输入剧本</div>
                <div className="mt-1 text-xs leading-5 text-dim">支持角色名 + 冒号台词，以及“第一场/第二场”分场标题。</div>
              </div>
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                accept=".txt,.md,.markdown,.pdf"
                onChange={(event) => {
                  void upload(event.target.files?.[0]);
                }}
              />
              <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
                <FileUp size={15} /> 上传文件
              </Button>
            </div>

            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_96px]">
              <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="剧本名称" />
              <Input value={versionLabel} onChange={(event) => setVersionLabel(event.target.value)} placeholder="版本" />
            </div>

            <Textarea
              value={scriptText}
              onChange={(event) => setScriptText(event.target.value)}
              className="min-h-[470px] flex-1 resize-y rounded-2xl font-serif leading-7"
              spellCheck={false}
              placeholder="把剧本粘贴到这里…"
            />

            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" className="text-xs text-dim hover:text-primary" onClick={() => setScriptText(DEMO_SCRIPT)}>
                载入示例剧本
              </button>
              <Button type="button" onClick={() => void analyze()} disabled={busy || !scriptText.trim()}>
                {busy ? <Loader2 className="animate-spin" /> : <Play />}
                {busy ? "Agent 分析中…" : "运行解析 Agent"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="min-h-[680px] overflow-hidden">
          <CardContent className="h-full p-4 md:p-5">
            {!analysis ? (
              <div className="flex h-full min-h-[640px] flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary">
                  <Orbit size={30} />
                </div>
                <div className="mt-5 text-xl font-semibold">等待一次 Agent 运行</div>
                <p className="mt-2 max-w-md text-sm leading-6 text-dim">
                  解析完成后，这里会展示场次、角色、台词、道具以及每一步 Agent trace。每条台词都能回指原剧本行号。
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-lg font-semibold">{analysis.title}</div>
                    <div className="mt-1 text-xs text-dim">版本 {analysis.version_label} · {analysis.analysis_mode} parser · {analysis.parser_version}</div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">{analysis.scenes.length} 场</span>
                    <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{analysis.characters.length} 角色</span>
                    <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">{analysis.props.length} 道具</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {analysis.trace.map((step) => (
                    <span key={step.name} className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px]",
                      step.status === "repaired" ? "border-orange/25 bg-orange/8 text-orange" : "border-green/25 bg-green/8 text-green",
                    )}>
                      <CheckCircle2 size={12} />
                      {TRACE_LABELS[step.name] || step.name}
                    </span>
                  ))}
                </div>

                {analysis.warnings.length > 0 && (
                  <div className="rounded-xl border border-orange/25 bg-orange/8 px-3 py-2.5 text-xs leading-5 text-orange">
                    {analysis.warnings.map((warning) => <div key={warning}>· {warning}</div>)}
                  </div>
                )}

                <div className="grid gap-3 sm:grid-cols-2">
                  <SummaryBlock icon={Users} label="角色" values={analysis.characters.map((item) => `${item.name} · ${item.dialogue_count}句`)} />
                  <SummaryBlock icon={Package} label="道具" values={analysis.props.map((item) => `${item.name} · ${item.mention_count}次`)} />
                </div>

                <div className="space-y-3">
                  <div className="text-sm font-semibold">场次与台词</div>
                  {analysis.scenes.map((scene) => (
                    <div key={scene.scene_id} className="rounded-2xl border border-border bg-background/45 p-3.5">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="font-semibold">第 {scene.number} 场 · {scene.title}</div>
                          <div className="mt-1 text-[11px] text-dim">原文第 {scene.source.start_line}–{scene.source.end_line} 行 · {scene.lines.length} 句台词</div>
                        </div>
                        <div className="flex flex-wrap justify-end gap-1">
                          {scene.characters.map((character) => <span key={character} className="rounded-full bg-teal/10 px-2 py-0.5 text-[10px] text-teal">{character}</span>)}
                          {scene.props.map((prop) => <span key={prop} className="rounded-full bg-orange/10 px-2 py-0.5 text-[10px] text-orange">道具·{prop}</span>)}
                        </div>
                      </div>
                      <div className="mt-3 space-y-2">
                        {scene.lines.slice(0, 6).map((line) => (
                          <div key={line.line_id} className="rounded-xl bg-hover/55 px-3 py-2 text-sm leading-6">
                            <span className="mr-2 font-semibold text-primary">{line.character}</span>
                            <span>{line.text}</span>
                            <span className="ml-2 text-[10px] text-dim">L{line.source.start_line}</span>
                          </div>
                        ))}
                        {scene.lines.length > 6 && <div className="text-center text-[11px] text-dim">还有 {scene.lines.length - 6} 句台词未展开</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SummaryBlock({
  icon: Icon,
  label,
  values,
}: {
  icon: typeof Users;
  label: string;
  values: string[];
}) {
  return (
    <div className="rounded-2xl border border-border bg-background/45 p-3.5">
      <div className="flex items-center gap-2 text-xs font-semibold">
        <Icon size={15} className="text-primary" />
        {label}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.length > 0 ? values.map((value) => <span key={value} className="rounded-full bg-hover px-2 py-1 text-[11px] text-dim">{value}</span>) : <span className="text-xs text-dim">暂未识别</span>}
      </div>
    </div>
  );
}
