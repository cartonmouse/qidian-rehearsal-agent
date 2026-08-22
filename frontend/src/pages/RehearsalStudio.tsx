import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Download,
  FileUp,
  Layers3,
  ListChecks,
  Loader2,
  Orbit,
  Package,
  Pencil,
  Play,
  Save,
  X,
  Users,
} from "lucide-react";

import {
  parseScript,
  parseScriptFile,
  planSchedule as planScheduleApi,
  getAvailability,
  reviewScript,
  saveAvailability,
  generateScheduleDraft,
  type AvailabilitySlot,
  type SceneReviewPatch,
  type ScriptAnalysis,
  type ScheduleDraft,
  type ScheduleToolCall,
} from "@/api/rehearsal";
import {
  formatAvailabilityCsv,
  formatAvailabilityText,
  parseAvailabilityImport,
  parseAvailabilityText,
} from "@/lib/rehearsal";
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

const ANALYSIS_MODE_LABELS: Record<ScriptAnalysis["analysis_mode"], string> = {
  deterministic: "规则解析",
  llm: "LLM 结构化解析",
  hybrid: "LLM + 规则降级",
};

const REVIEW_STATUS_LABELS: Record<ScriptAnalysis["review_status"], string> = {
  pending: "待人工确认",
  confirmed: "已确认",
  edited: "已人工修改",
};

const SCHEDULE_TOOL_LABELS: Record<string, string> = {
  inspect_script: "检查确认门槛",
  extract_scene_requirements: "提取场次需求",
  group_parallel_tasks: "划分并行任务",
  validate_schedule_draft: "校验调度草案",
  find_common_actor_slot: "查找共同档期",
  validate_schedule: "校验排班结果",
  apply_manual_override: "应用人工覆盖",
};

const SCHEDULE_TOOL_PHASE_LABELS: Record<ScheduleToolCall["phase"], string> = {
  inspect: "检查",
  extract: "提取",
  group: "分组",
  assign: "排班",
  validate: "校验",
  override: "人工覆盖",
};

function formatScheduleToolResult(call: ScheduleToolCall): string {
  const result = call.result;
  if (call.tool_name === "find_common_actor_slot") {
    if (result.status === "scheduled") {
      return `${String(result.date)} · ${String(result.start)}–${String(result.end)}`;
    }
    return String(result.reason || "保留未排班状态");
  }
  if (call.tool_name === "group_parallel_tasks") {
    return `${String(result.parallel_group_count || 0)} 个并行组`;
  }
  if (call.tool_name === "validate_schedule") {
    return `已排 ${String(result.scheduled_count || 0)} · 未排 ${String(result.unassigned_count || 0)} · 冲突 ${String(result.overlap_count || 0)}`;
  }
  if (call.tool_name === "apply_manual_override") {
    return `人工确认 · ${String(result.duration_minutes || 0)} 分钟`;
  }
  if (call.tool_name === "extract_scene_requirements") {
    const characters = Array.isArray(result.required_characters) ? result.required_characters.length : 0;
    const props = Array.isArray(result.props) ? result.props.length : 0;
    return `${characters} 名演员 · ${props} 件道具 · ${String(result.estimated_minutes || 0)} 分钟`;
  }
  return result.review_gate === "passed" ? "确认门槛通过" : call.tool_name === "inspect_script" ? "仅允许预览" : "结构校验通过";
}

function splitLabels(value: string): string[] {
  return value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, items) => items.indexOf(item) === index);
}

export default function RehearsalStudio() {
  const [title, setTitle] = useState("轨道之外");
  const [versionLabel, setVersionLabel] = useState("v1");
  const [scriptText, setScriptText] = useState(DEMO_SCRIPT);
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [schedule, setSchedule] = useState<ScheduleDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [availabilitySaving, setAvailabilitySaving] = useState(false);
  const [availabilityText, setAvailabilityText] = useState("");
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, SceneReviewPatch>>({});
  const [reviewNote, setReviewNote] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const [availabilityMessage, setAvailabilityMessage] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const availabilityFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void getAvailability()
      .then((slots) => {
        if (!cancelled) setAvailabilityText(formatAvailabilityText(slots));
      })
      .catch(() => {
        // The time pool is an optional enhancement; local input remains usable if it cannot be loaded.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function analyze() {
    const value = scriptText.trim();
    if (!value) {
      setError("请先输入剧本文本");
      return;
    }
    setBusy(true);
    setError("");
    setReviewMessage("");
    setSchedule(null);
    try {
      const result = await parseScript({
        title: title.trim() || "未命名剧本",
        version_label: versionLabel.trim() || "v1",
        script_text: value,
      });
      setAnalysis(result);
      setSchedule(null);
      setReviewing(false);
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
    setReviewMessage("");
    try {
      const result = await parseScriptFile(file, versionLabel.trim() || "v1");
      setTitle(result.title);
      setScriptText(`已上传 ${file.name}，解析结果已保存。`);
      setAnalysis(result);
      setReviewing(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件解析失败");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function startReview() {
    if (!analysis) return;
    const drafts = Object.fromEntries(
      analysis.scenes.map((scene) => [scene.scene_id, {
        scene_id: scene.scene_id,
        title: scene.title,
        characters: [...scene.characters],
        props: [...scene.props],
      }]),
    );
    setReviewDrafts(drafts);
    setReviewNote(analysis.review_note || "");
    setReviewMessage("");
    setReviewing(true);
  }

  function cancelReview() {
    setReviewing(false);
    setReviewDrafts({});
    setReviewMessage("");
  }

  function updateReviewDraft(sceneId: string, patch: Partial<SceneReviewPatch>) {
    setReviewDrafts((current) => ({
      ...current,
      [sceneId]: { ...current[sceneId], ...patch },
    }));
  }

  async function submitReview(status: "confirmed" | "edited") {
    if (!analysis) return;
    setBusy(true);
    setError("");
    try {
      const updated = await reviewScript(analysis.script_id, {
        scenes: analysis.scenes.map((scene) => reviewDrafts[scene.scene_id]),
        review_status: status,
        review_note: reviewNote.trim(),
      });
      setAnalysis(updated);
      setSchedule(null);
      setReviewing(false);
      setReviewDrafts({});
      setReviewMessage(status === "edited" ? "人工修改已保存，剧本结构可以进入排练调度。" : "已确认解析结果，可以进入排练调度。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审核结果保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function generateSchedule(preview = false) {
    if (!analysis) return;
    setScheduling(true);
    setError("");
    try {
      setSchedule(await generateScheduleDraft(analysis.script_id, 45, preview));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "排练调度草案生成失败");
    } finally {
      setScheduling(false);
    }
  }

  async function planWithAvailability() {
    if (!analysis) return;
    let slots: AvailabilitySlot[];
    try {
      slots = parseAvailabilityText(availabilityText);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "可用时间格式错误");
      return;
    }
    setPlanning(true);
    setError("");
    try {
      setSchedule(await planScheduleApi(analysis.script_id, slots));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自动排班失败");
    } finally {
      setPlanning(false);
    }
  }

  async function persistAvailability() {
    let slots: AvailabilitySlot[];
    try {
      slots = parseAvailabilityText(availabilityText);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "演员档期格式错误");
      return;
    }
    setAvailabilitySaving(true);
    setError("");
    try {
      const saved = await saveAvailability(slots);
      setAvailabilityText(formatAvailabilityText(saved));
      setAvailabilityMessage(`已保存 ${saved.length} 条演员可用时间，可供不同剧本重复使用。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "演员档期保存失败");
    } finally {
      setAvailabilitySaving(false);
    }
  }

  async function importAvailability(file?: File) {
    if (!file) return;
    setError("");
    setAvailabilityMessage("");
    try {
      const imported = parseAvailabilityImport(await file.text());
      setAvailabilityText(formatAvailabilityText(imported));
      setAvailabilityMessage(`已导入 ${imported.length} 条档期记录，请确认后保存。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "档期文件解析失败");
    } finally {
      if (availabilityFileRef.current) availabilityFileRef.current.value = "";
    }
  }

  function downloadAvailabilityTemplate() {
    const blob = new Blob([`\uFEFF${formatAvailabilityCsv([])}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "qidian-actor-availability-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  const hasAnalysis = Boolean(analysis);
  const isReviewed = Boolean(analysis && analysis.review_status !== "pending");
  const hasSchedule = Boolean(schedule);
  const isSchedulePreview = Boolean(schedule?.is_preview);
  const hasScheduledTasks = Boolean(schedule?.tasks.some((task) => task.status === "scheduled"));

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Orbit className="text-primary" size={30} />
            排练工作台
          </div>
          <div className="mt-1 text-sm leading-6 text-dim">
            剧本解读 Agent：把文本变成可核对、可调度的排练结构。
          </div>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          当前节点 · 剧本解析
        </div>
      </div>

      <div className="rounded-2xl border border-primary/20 bg-primary/5 p-3.5 md:p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Orbit size={16} className="text-primary" />
              推荐路径（可跳过）
            </div>
            <div className="mt-1 text-xs leading-5 text-dim">
              这是质量控制的推荐顺序，不是唯一入口；演员时间池可独立维护，未确认剧本也可以先生成调度预览。
            </div>
          </div>
          <div className="text-[11px] text-primary">
            {!hasAnalysis ? "第 1 步 / 4 步" : !isReviewed ? "第 2 步 / 4 步" : !hasSchedule ? "第 3 步 / 4 步" : "第 4 步 / 4 步"}
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <WorkflowStep number="01" title="解析剧本" detail="分场 · 角色 · 道具" active={!hasAnalysis} done={hasAnalysis} />
          <WorkflowStep number="02" title="人工确认" detail="标题 · 角色 · 道具可修改" active={hasAnalysis && !isReviewed} done={isReviewed} />
          <WorkflowStep number="03" title={isSchedulePreview ? "调度预览" : "调度 Agent"} detail="任务 · 清单 · 时长 · 并行组" active={isReviewed && !hasSchedule || isSchedulePreview} done={hasSchedule} />
          <WorkflowStep number="04" title="自动排班" detail="可用时间 · 未排班原因" active={hasSchedule && !hasScheduledTasks} done={hasScheduledTasks} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-primary/15 pt-3">
          {!analysis ? (
            <Button type="button" size="sm" onClick={() => void analyze()} disabled={busy || !scriptText.trim()}>
              {busy ? <Loader2 className="animate-spin" /> : <Play size={14} />}
              开始：运行解析 Agent
            </Button>
          ) : !isReviewed ? (
            <>
              <Button type="button" size="sm" onClick={startReview} disabled={busy || reviewing || scheduling}>
                <Pencil size={14} /> 去人工确认场次
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => void generateSchedule(true)} disabled={scheduling || reviewing}>
                {scheduling ? <Loader2 className="animate-spin" /> : <Layers3 size={14} />}
                预览调度（未确认）
              </Button>
            </>
          ) : !schedule ? (
            <Button type="button" size="sm" onClick={() => void generateSchedule()} disabled={scheduling || reviewing}>
              {scheduling ? <Loader2 className="animate-spin" /> : <Layers3 size={14} />}
              生成排练调度草案
            </Button>
          ) : (
            <span className="text-xs text-dim">下一步：在上方“演员时间池”中填写时间段，然后点击“自动排班当前任务”。</span>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="p-3.5 md:p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold">
                <CalendarClock size={16} className="text-primary" />
                演员时间池
                <span className="rounded-full border border-teal/25 bg-teal/8 px-2 py-0.5 text-[10px] font-normal text-teal">可独立维护</span>
              </div>
              <div className="mt-1 text-xs leading-5 text-dim">
                不依赖剧本解析。支持导入表格，先收集演员可用时间，保存后可以被不同剧本重复使用。
              </div>
            </div>
            <input
              ref={availabilityFileRef}
              type="file"
              className="hidden"
              accept=".csv,.tsv,.txt"
              onChange={(event) => void importAvailability(event.target.files?.[0])}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => availabilityFileRef.current?.click()} disabled={availabilitySaving || planning}>
                <FileUp size={14} /> 导入 CSV/TSV
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={downloadAvailabilityTemplate} disabled={availabilitySaving}>
                <Download size={14} /> 下载模板
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => void persistAvailability()} disabled={availabilitySaving || planning}>
                {availabilitySaving ? <Loader2 className="animate-spin" /> : <Save size={14} />}
                保存演员档期
              </Button>
              {schedule && (
                <Button type="button" size="sm" onClick={() => void planWithAvailability()} disabled={planning || reviewing || availabilitySaving}>
                  {planning ? <Loader2 className="animate-spin" /> : <CalendarClock size={14} />}
                  自动排班当前任务
                </Button>
              )}
            </div>
          </div>
          <Textarea
            value={availabilityText}
            onChange={(event) => {
              setAvailabilityText(event.target.value);
              setAvailabilityMessage("");
              setError("");
            }}
            className="mt-3 min-h-24 rounded-xl font-mono text-xs leading-6"
            placeholder={'演员,日期,开始时间,结束时间\n小林,2026-08-25,19:00,21:00\n导演,2026-08-25,19:00,21:00'}
          />
          {availabilityMessage && <div className="mt-2 text-xs text-green">{availabilityMessage}</div>}
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {reviewMessage && (
        <div className="flex items-center gap-2 rounded-xl border border-green/25 bg-green/8 px-4 py-2.5 text-sm text-green">
          <CheckCircle2 size={16} />
          {reviewMessage}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.4fr)]">
        <Card className="min-h-[680px] overflow-hidden">
          <CardContent className="flex h-full flex-col gap-4 p-4 md:p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">输入剧本</div>
                <div className="mt-1 text-xs leading-5 text-dim">粘贴剧本后运行 Agent；支持角色名 + 冒号台词，以及“第一场/第二场”分场标题。</div>
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
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
                  <FileUp size={15} /> 上传文件
                </Button>
                <Button type="button" size="sm" onClick={() => void analyze()} disabled={busy || !scriptText.trim()}>
                  {busy ? <Loader2 className="animate-spin" /> : <Play size={15} />}
                  {busy ? "分析中…" : "运行解析 Agent"}
                </Button>
              </div>
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
              <span className="text-[11px] text-dim">运行后可人工确认场次，也可以先预览调度结果。</span>
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
                  点击页面上方或左侧的“运行解析 Agent”后，这里会展示场次、角色、台词、道具以及每一步 Agent trace。确认场次后还能继续生成调度任务和自动排班。
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-lg font-semibold">{analysis.title}</div>
                    <div className="mt-1 text-xs text-dim">版本 {analysis.version_label} · {ANALYSIS_MODE_LABELS[analysis.analysis_mode]} · {analysis.parser_version}</div>
                    <div className="mt-2 inline-flex rounded-full border border-primary/20 bg-primary/8 px-2.5 py-1 text-[11px] text-primary">
                      {REVIEW_STATUS_LABELS[analysis.review_status]}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">{analysis.scenes.length} 场</span>
                    <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{analysis.characters.length} 角色</span>
                    <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">{analysis.props.length} 道具</span>
                    {!reviewing ? (
                      <Button type="button" variant="outline" size="sm" onClick={startReview} disabled={busy}>
                        <Pencil size={14} /> 人工确认
                      </Button>
                    ) : (
                      <>
                        <Button type="button" variant="outline" size="sm" onClick={cancelReview} disabled={busy}>
                          <X size={14} /> 取消
                        </Button>
                        <Button type="button" variant="outline" size="sm" onClick={() => void submitReview("confirmed")} disabled={busy}>
                          <CheckCircle2 size={14} /> 确认无误
                        </Button>
                        <Button type="button" size="sm" onClick={() => void submitReview("edited")} disabled={busy}>
                          {busy ? <Loader2 className="animate-spin" /> : <Save size={14} />} 保存修改
                        </Button>
                      </>
                    )}
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

                {reviewing && (
                  <div className="rounded-2xl border border-primary/20 bg-primary/5 p-3.5">
                    <div className="text-sm font-semibold">人工确认节点</div>
                    <div className="mt-1 text-xs leading-5 text-dim">可以修改每场的标题、角色和道具；台词原文与行号保持不变，作为后续调度的证据。</div>
                    <Textarea
                      value={reviewNote}
                      onChange={(event) => setReviewNote(event.target.value)}
                      className="mt-3 min-h-20 rounded-xl"
                      placeholder="审核备注（可选）：例如第一场需要导演、演员小林到场。"
                    />
                  </div>
                )}

                <div className="space-y-3">
                  <div className="text-sm font-semibold">场次与台词</div>
                  {analysis.scenes.map((scene) => {
                    const draft = reviewDrafts[scene.scene_id];
                    return (
                    <div key={scene.scene_id} className="rounded-2xl border border-border bg-background/45 p-3.5">
                      {reviewing && draft ? (
                        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                          <Input
                            value={draft.title}
                            onChange={(event) => updateReviewDraft(scene.scene_id, { title: event.target.value })}
                            placeholder="场次标题"
                          />
                          <Input
                            value={draft.characters.join("、")}
                            onChange={(event) => updateReviewDraft(scene.scene_id, { characters: splitLabels(event.target.value) })}
                            placeholder="角色，用顿号或逗号分隔"
                          />
                          <Input
                            value={draft.props.join("、")}
                            onChange={(event) => updateReviewDraft(scene.scene_id, { props: splitLabels(event.target.value) })}
                            placeholder="道具，用顿号或逗号分隔"
                          />
                        </div>
                      ) : (
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
                      )}
                      {reviewing && draft && (
                        <div className="mt-2 text-[11px] text-dim">第 {scene.number} 场 · 原文第 {scene.source.start_line}–{scene.source.end_line} 行 · {scene.lines.length} 句台词</div>
                      )}
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
                    );
                  })}
                </div>

                {(analysis.review_status !== "pending" || schedule) && (
                  <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <CalendarClock size={16} className="text-primary" />
                          排练调度 Agent
                          {schedule?.is_preview && (
                            <span className="rounded-full border border-orange/25 bg-orange/10 px-2 py-0.5 text-[10px] font-normal text-orange">未确认预览</span>
                          )}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-dim">
                          {schedule?.is_preview
                            ? "这是基于当前解析结果的预览，允许你先检查任务和并行组；确认场次后再生成正式草案。"
                            : "根据已确认的场次、演员和道具生成排练任务草案，并用资源冲突划分并行组。"}
                        </div>
                      </div>
                      <Button type="button" variant="outline" size="sm" onClick={() => void generateSchedule(analysis.review_status === "pending")} disabled={scheduling || reviewing}>
                        {scheduling ? <Loader2 className="animate-spin" /> : <Layers3 size={14} />}
                        {schedule ? (schedule.is_preview ? "重新生成预览" : "重新生成草案") : "生成调度草案"}
                      </Button>
                    </div>

                    {!schedule ? (
                      <div className="mt-4 rounded-xl border border-border/70 bg-background/40 px-3 py-3 text-xs text-dim">
                      调度 Agent 尚未运行。可以先生成未确认预览，也可以确认场次后生成正式排练任务。
                      </div>
                    ) : (
                      <div className="mt-4 space-y-3">
                        <div className="flex flex-wrap gap-2 text-[11px] text-dim">
                          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">{schedule.tasks.length} 个场次任务</span>
                          <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{new Set(schedule.tasks.map((task) => task.parallel_group)).size} 个并行组</span>
                          <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">{schedule.tool_calls?.length ?? 0} 次工具调用</span>
                        </div>
                        {schedule.resource_context && (
                          <div className="rounded-xl border border-border bg-background/35 px-3 py-2.5 text-[11px] leading-5 text-dim">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-medium text-text">资源上下文快照</span>
                              <span>配乐 {schedule.resource_context.music_cues.length} 个提示点 · 预算 {schedule.resource_context.budget_items.length} 项 · 发票 {schedule.resource_context.invoices.length} 张 · 服装 {schedule.resource_context.costume_inventory.length} 条</span>
                            </div>
                            <div className="mt-1">预计 ¥{schedule.resource_context.estimated_total.toFixed(2)} · 实际 ¥{schedule.resource_context.actual_total.toFixed(2)} · 发票 ¥{schedule.resource_context.invoice_total.toFixed(2)}（已核验 ¥{schedule.resource_context.verified_invoice_total.toFixed(2)}）· 服装待处理 {schedule.resource_context.costume_issue_count} 项 · 生成草案时读取，资源变更后请重新生成。</div>
                            {schedule.resource_context.warnings.map((warning) => <div key={warning} className="mt-1 rounded-md bg-red/8 px-2 py-1 text-red">{warning}</div>)}
                          </div>
                        )}
                        {schedule.agent_run_id && (
                          <div className="flex flex-wrap gap-2 text-[11px] text-dim">
                            <span className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1">当前 Run · {schedule.agent_run_id}</span>
                            {schedule.parent_run_id && <span className="rounded-full border border-border/70 bg-background/30 px-2.5 py-1">上游 Run · {schedule.parent_run_id}</span>}
                          </div>
                        )}
                        {(schedule.tool_calls?.length ?? 0) > 0 && (
                          <div className="rounded-xl border border-border bg-background/35 p-3">
                            <div className="flex items-center gap-2 text-xs font-semibold">
                              <ListChecks size={15} className="text-primary" />
                              调度 Agent 工具调用链
                              <span className="text-[10px] font-normal text-dim">每一步都保留参数结果和解释</span>
                            </div>
                            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                              {schedule.tool_calls.map((call, index) => (
                                <div key={call.call_id} className="rounded-lg border border-border/80 bg-background/50 px-2.5 py-2">
                                  <div className="flex items-center gap-2 text-[11px]">
                                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/12 font-mono text-[10px] text-primary">{String(index + 1).padStart(2, "0")}</span>
                                    <span className="font-semibold">{SCHEDULE_TOOL_LABELS[call.tool_name] || call.tool_name}</span>
                                    <span className="ml-auto rounded-full bg-hover px-1.5 py-0.5 text-[10px] text-dim">{SCHEDULE_TOOL_PHASE_LABELS[call.phase]}</span>
                                  </div>
                                  <div className="mt-1.5 text-[11px] leading-5 text-dim">{call.summary}</div>
                                  <div className={cn("mt-1 text-[10px]", call.status === "repaired" ? "text-orange" : call.status === "failed" ? "text-red" : "text-teal")}>
                                    结果：{formatScheduleToolResult(call)}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="grid gap-2 md:grid-cols-2">
                          {schedule.tasks.map((task) => (
                            <div key={task.task_id} className="rounded-xl border border-border bg-background/45 p-3">
                              <div className="flex items-start justify-between gap-2">
                                <div className="text-sm font-semibold">第 {task.scene_number} 场 · {task.title}</div>
                                <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">并行组 {task.parallel_group}</span>
                              </div>
                              <div className="mt-2 flex items-center gap-1.5 text-[11px] text-dim">
                                <Clock3 size={13} /> 预计 {task.estimated_minutes} 分钟
                              </div>
                              <div className="mt-2 text-[11px] leading-5 text-dim">{task.parallel_reason || "按演员和道具资源划分并行组"}</div>
                              {task.status === "scheduled" ? (
                                <div className="mt-2 rounded-lg bg-green/8 px-2 py-1.5 text-xs text-green">
                                  已排班：{task.scheduled_date} · {task.scheduled_start}–{task.scheduled_end}
                                </div>
                              ) : task.status === "overridden" ? (
                                <div className="mt-2 rounded-lg bg-primary/8 px-2 py-1.5 text-xs text-primary">
                                  人工覆盖：{task.scheduled_date} · {task.scheduled_start}–{task.scheduled_end}
                                </div>
                              ) : task.status === "unassigned" ? (
                                <div className="mt-2 rounded-lg bg-red/8 px-2 py-1.5 text-xs text-red">
                                  未排班：{task.unassigned_reason}
                                </div>
                              ) : null}
                              {task.status === "unassigned" && task.alternatives?.length > 0 && (
                                <div className="mt-2 rounded-lg border border-orange/20 bg-orange/6 px-2 py-1.5 text-[11px] leading-5 text-orange">
                                  候选方案：{task.alternatives.map((alternative) => alternative.label).join("；")}
                                </div>
                              )}
                              <div className="mt-2 text-xs leading-5 text-dim">
                                演员：{task.required_characters.length > 0 ? task.required_characters.join("、") : "待确认"}
                              </div>
                              <div className="text-xs leading-5 text-dim">
                                道具：{task.props.length > 0 ? task.props.join("、") : "无"}
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="rounded-xl border border-border bg-background/35 px-3 py-2.5 text-xs leading-5 text-dim">
                          排班使用页面上方的“演员时间池”。你可以先保存演员档期，再回来生成任务；生成任务后点击上方“自动排班当前任务”即可。
                        </div>
                      </div>
                    )}
                  </div>
                )}
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

function WorkflowStep({
  number,
  title,
  detail,
  active,
  done,
}: {
  number: string;
  title: string;
  detail: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div className={cn(
      "rounded-xl border px-3 py-2.5",
      active ? "border-primary/35 bg-primary/10" : done ? "border-green/25 bg-green/8" : "border-border bg-background/35",
    )}>
      <div className="flex items-center gap-2">
        <span className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold",
          active ? "bg-primary text-primary-foreground" : done ? "bg-green/15 text-green" : "bg-hover text-dim",
        )}>
          {done ? "✓" : number}
        </span>
        <span className="text-xs font-semibold">{title}</span>
      </div>
      <div className="mt-1 pl-7 text-[10px] leading-4 text-dim">{detail}</div>
    </div>
  );
}
