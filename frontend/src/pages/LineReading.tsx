import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Loader2,
  MessageCircle,
  Play,
  RotateCcw,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getScript,
  getScripts,
  readLine,
  type LineReadingResponse,
  type ScriptAnalysis,
  type ScriptSummary,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

type TranscriptItem =
  | { kind: "partner"; character: string; text: string; sourceLine: number }
  | { kind: "actor"; character: string; text: string }
  | { kind: "feedback"; text: string };

const ENGINE_LABELS: Record<LineReadingResponse["engine"], string> = {
  strict: "原词推进",
  llm: "LLM 适应性回应",
  fallback: "规则降级",
};

export default function LineReading() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [sceneId, setSceneId] = useState("");
  const [character, setCharacter] = useState("");
  const [mode, setMode] = useState<"strict" | "adaptive">("strict");
  const [lineIndex, setLineIndex] = useState(0);
  const [actorPrompt, setActorPrompt] = useState<LineReadingResponse["actor_prompt"]>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [actorText, setActorText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedScene = useMemo(
    () => analysis?.scenes.find((scene) => scene.scene_id === sceneId) || null,
    [analysis, sceneId],
  );
  const sceneCharacters = useMemo(() => {
    if (!selectedScene) return [];
    return selectedScene.lines.map((line) => line.character)
      .map((item) => item.trim())
      .filter(Boolean)
      .filter((item, index, items) => items.indexOf(item) === index);
  }, [selectedScene]);

  const resetSession = useCallback(() => {
    setLineIndex(0);
    setActorPrompt(null);
    setTranscript([]);
    setActorText("");
    setMessage("");
    setError("");
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getScripts()
      .then((items) => {
        if (cancelled) return;
        setScripts(items);
        setSelectedScriptId((current) => (
          current && items.some((item) => item.script_id === current)
            ? current
            : items[0]?.script_id || ""
        ));
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

  useEffect(() => {
    if (!selectedScriptId) {
      setAnalysis(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getScript(selectedScriptId)
      .then((item) => {
        if (cancelled) return;
        setAnalysis(item);
        const firstScene = item.scenes[0];
        setSceneId(firstScene?.scene_id || "");
        setCharacter(firstScene?.characters[0] || firstScene?.lines[0]?.character || "");
        resetSession();
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本详情加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [resetSession, selectedScriptId]);

  function changeScene(value: string) {
    const nextScene = analysis?.scenes.find((scene) => scene.scene_id === value);
    setSceneId(value);
    setCharacter(nextScene?.characters[0] || nextScene?.lines[0]?.character || "");
    resetSession();
  }

  function changeCharacter(value: string) {
    setCharacter(value);
    resetSession();
  }

  function changeMode(value: "strict" | "adaptive") {
    setMode(value);
    resetSession();
  }

  async function advance(userText = "", startingIndex?: number, replaceTranscript = false) {
    if (!analysis || !selectedScene || !character) return;
    const currentLineIndex = startingIndex ?? lineIndex;
    if (startingIndex === undefined && actorPrompt && !userText.trim()) {
      setError("请先输入本句台词，再继续对词");
      return;
    }
    setSessionLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await readLine(analysis.script_id, {
        scene_id: selectedScene.scene_id,
        character,
        mode,
        line_index: currentLineIndex,
        user_text: userText,
      });
      const additions: TranscriptItem[] = [];
      if (userText.trim()) additions.push({ kind: "actor", character, text: userText.trim() });
      result.assistant_turns.forEach((turn) => additions.push({
        kind: "partner",
        character: turn.character,
        text: turn.text,
        sourceLine: turn.source_line,
      }));
      if (result.feedback) additions.push({ kind: "feedback", text: result.feedback });
      setTranscript((current) => replaceTranscript ? additions : [...current, ...additions]);
      setActorPrompt(result.actor_prompt);
      setLineIndex(result.next_line_index ?? selectedScene.lines.length);
      setActorText("");
      setMessage(result.note || ENGINE_LABELS[result.engine]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "对词 Agent 运行失败");
    } finally {
      setSessionLoading(false);
    }
  }

  const hasSession = transcript.length > 0 || actorPrompt !== null;
  const finished = hasSession && actorPrompt === null && lineIndex >= (selectedScene?.lines.length || 0);

  function startOrRestart() {
    if (hasSession) {
      resetSession();
      void advance("", 0, true);
      return;
    }
    void advance();
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <MessageCircle className="text-primary" size={30} />
            对词训练
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            选择一个角色，按场次逐句练习。原词模式稳定可用，适应性模式让 LLM 根据你的表达继续回应。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          对词 Agent
        </div>
      </header>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {message && !error && (
        <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green">
          <CheckCircle2 size={16} />
          {message}
        </div>
      )}

      {loading ? (
        <Card className="min-h-[520px]">
          <CardContent className="flex min-h-[520px] items-center justify-center text-sm text-dim">
            <Loader2 className="mr-2 animate-spin" size={18} /> 正在读取剧本
          </CardContent>
        </Card>
      ) : !analysis ? (
        <EmptyReadingState onNavigate={() => navigate("/rehearsal")} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.72fr)_minmax(560px,1.28fr)]">
          <div className="space-y-4">
            <Card>
              <CardContent className="space-y-4 p-4 md:p-5">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <BookOpen size={16} className="text-primary" />
                    练习设置
                  </div>
                  <p className="mt-1 text-xs leading-5 text-dim">对词会读取已保存的剧本原文和场次结构，不会改写剧本数据。</p>
                </div>

                <FieldLabel label="剧本">
                  <select
                    value={selectedScriptId}
                    onChange={(event) => setSelectedScriptId(event.target.value)}
                    className="h-10 w-full rounded-lg border border-input bg-input-bg px-3 text-sm text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  >
                    {scripts.map((script) => <option key={script.script_id} value={script.script_id}>{script.title} · {script.version_label}</option>)}
                  </select>
                </FieldLabel>

                <FieldLabel label="场次">
                  <select
                    value={sceneId}
                    onChange={(event) => changeScene(event.target.value)}
                    className="h-10 w-full rounded-lg border border-input bg-input-bg px-3 text-sm text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  >
                    {analysis.scenes.map((scene) => <option key={scene.scene_id} value={scene.scene_id}>第 {scene.number} 场 · {scene.title}</option>)}
                  </select>
                </FieldLabel>

                <FieldLabel label="我的角色">
                  <select
                    value={character}
                    onChange={(event) => changeCharacter(event.target.value)}
                    className="h-10 w-full rounded-lg border border-input bg-input-bg px-3 text-sm text-text outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                  >
                    {sceneCharacters.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </FieldLabel>

                <div>
                  <div className="mb-2 text-xs font-medium text-dim">练习模式</div>
                  <div className="grid grid-cols-2 gap-2">
                    <ModeButton active={mode === "strict"} onClick={() => changeMode("strict")} title="原词模式" detail="严格保留原台词" />
                    <ModeButton active={mode === "adaptive"} onClick={() => changeMode("adaptive")} title="适应性模式" detail="LLM 顺着语义回应" />
                  </div>
                </div>

                {selectedScene && (
                  <div className="rounded-xl border border-border bg-background/35 px-3 py-3 text-xs leading-5 text-dim">
                    <div className="flex items-center justify-between gap-2 text-text">
                      <span>当前场次原文</span>
                      <span>{selectedScene.lines.length} 句台词</span>
                    </div>
                    <div className="mt-2 line-clamp-5 font-serif text-sm leading-6 text-dim">
                      {selectedScene.lines.map((line) => `${line.character}：${line.text}`).join("\n")}
                    </div>
                  </div>
                )}

                <Button type="button" className="w-full" onClick={startOrRestart} disabled={sessionLoading || !selectedScene || !character}>
                  {sessionLoading ? <Loader2 className="animate-spin" /> : <Play size={15} />}
                  {hasSession ? "从头开始" : "开始对词"}
                </Button>
                {hasSession && (
                  <Button type="button" variant="ghost" className="w-full" onClick={resetSession} disabled={sessionLoading}>
                    <RotateCcw size={14} /> 清空本轮记录
                  </Button>
                )}
              </CardContent>
            </Card>

            <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 text-xs leading-5 text-dim">
              <div className="flex items-center gap-2 font-semibold text-primary"><Sparkles size={15} /> Agent 行为边界</div>
              <div className="mt-2">原始台词和行号始终来自剧本。适应性模式只改写对方回应，不会替换你的角色台词，也不会改变剧本存档。</div>
            </div>
          </div>

          <Card className="min-h-[680px] overflow-hidden">
            <CardContent className="flex min-h-[680px] flex-col p-4 md:p-5">
              <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold"><UserRound size={16} className="text-teal" /> {character || "选择角色"}</div>
                  <div className="mt-1 text-xs text-dim">{selectedScene ? `第 ${selectedScene.number} 场 · ${selectedScene.title}` : "等待选择场次"}</div>
                </div>
                <div className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] text-primary">
                  {selectedScene ? `${Math.min(lineIndex + 1, selectedScene.lines.length)} / ${selectedScene.lines.length}` : "0 / 0"}
                </div>
              </div>

              <div className="flex-1 space-y-3 overflow-y-auto py-4">
                {!hasSession ? (
                  <div className="flex min-h-[430px] items-center justify-center text-center">
                    <div className="max-w-sm">
                      <MessageCircle className="mx-auto text-primary" size={30} />
                      <div className="mt-4 text-lg font-semibold">等待开始对词</div>
                      <p className="mt-2 text-sm leading-6 text-dim">点击“开始对词”，Agent 会先给出对方角色台词，再把你的下一句原词交给你。</p>
                    </div>
                  </div>
                ) : transcript.length === 0 && actorPrompt ? (
                  <PromptCard prompt={actorPrompt} />
                ) : (
                  transcript.map((item, index) => <TranscriptCard key={`${item.kind}-${index}`} item={item} />)
                )}
                {hasSession && actorPrompt && transcript.length > 0 && <PromptCard prompt={actorPrompt} />}
                {finished && (
                  <div className="rounded-xl border border-green/25 bg-green/8 px-3 py-3 text-sm text-green">本场对词完成。可以重新开始，或切换其他场次。</div>
                )}
              </div>

              {hasSession && actorPrompt && !finished && (
                <div className="border-t border-border pt-4">
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs text-dim">
                    <span>轮到你：{actorPrompt.character}</span>
                    <span>原文第 {actorPrompt.source_line} 行</span>
                  </div>
                  <Textarea
                    value={actorText}
                    onChange={(event) => setActorText(event.target.value)}
                    className="min-h-24 rounded-xl font-serif leading-6"
                    placeholder={mode === "strict" ? "输入你读出的台词，系统会和原词做轻量比对" : "可以按自己的表达回应，Agent 会根据剧情意图继续"}
                  />
                  <Button type="button" className="mt-2 w-full" onClick={() => void advance(actorText)} disabled={sessionLoading || !actorText.trim()}>
                    {sessionLoading ? <Loader2 className="animate-spin" /> : <MessageCircle size={15} />}
                    提交台词并继续
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 text-xs font-medium text-dim">{label}</div>
      {children}
    </label>
  );
}

function ModeButton({ active, onClick, title, detail }: { active: boolean; onClick: () => void; title: string; detail: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border px-3 py-2.5 text-left transition-colors",
        active ? "border-primary/40 bg-primary/10 text-primary" : "border-border bg-background/35 text-dim hover:bg-hover hover:text-text",
      )}
    >
      <div className="text-xs font-semibold">{title}</div>
      <div className="mt-1 text-[10px] leading-4 opacity-80">{detail}</div>
    </button>
  );
}

function PromptCard({ prompt }: { prompt: NonNullable<LineReadingResponse["actor_prompt"]> }) {
  return (
    <div className="rounded-2xl border border-primary/25 bg-primary/8 p-4">
      <div className="flex items-center justify-between gap-2 text-xs text-primary">
        <span className="font-semibold">你的台词 · {prompt.character}</span>
        <span>原文第 {prompt.source_line} 行</span>
      </div>
      <div className="mt-2 font-serif text-lg leading-8 text-text">{prompt.text}</div>
    </div>
  );
}

function TranscriptCard({ item }: { item: TranscriptItem }) {
  if (item.kind === "feedback") {
    return <div className="rounded-xl bg-green/8 px-3 py-2 text-xs leading-5 text-green">{item.text}</div>;
  }
  if (item.kind === "actor") {
    return (
      <div className="ml-8 rounded-2xl border border-border bg-hover/45 p-3">
        <div className="text-xs font-semibold text-dim">你 · {item.character}</div>
        <div className="mt-1 text-sm leading-6 text-text">{item.text}</div>
      </div>
    );
  }
  return (
    <div className="mr-8 rounded-2xl border border-border bg-background/45 p-3">
      <div className="flex items-center justify-between gap-2 text-xs font-semibold text-teal">
        <span>{item.character}</span>
        <span className="font-normal text-dim">原文第 {item.sourceLine} 行</span>
      </div>
      <div className="mt-1 text-sm leading-6 text-text">{item.text}</div>
    </div>
  );
}

function EmptyReadingState({ onNavigate }: { onNavigate: () => void }) {
  return (
    <Card className="min-h-[520px]">
      <CardContent className="flex min-h-[520px] items-center justify-center text-center">
        <div className="max-w-sm">
          <BookOpen className="mx-auto text-primary" size={32} />
          <div className="mt-4 text-xl font-semibold">还没有可对词的剧本</div>
          <p className="mt-2 text-sm leading-6 text-dim">先到排练工作台粘贴或上传剧本，运行解析 Agent 后即可在这里选择场次和角色。</p>
          <Button type="button" className="mt-5" onClick={onNavigate}>去排练工作台</Button>
        </div>
      </CardContent>
    </Card>
  );
}
