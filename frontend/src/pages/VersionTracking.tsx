import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  GitBranch,
  Loader2,
  Minus,
  Package,
  PencilLine,
  Plus,
  Users,
} from "lucide-react";

import {
  compareScriptVersions,
  getScripts,
  type SceneDiff,
  type ScriptLineChange,
  type ScriptSummary,
  type ScriptVersionDiff,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useNavigate } from "react-router-dom";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

const STATUS_LABELS: Record<SceneDiff["status"], string> = {
  added: "新增场次",
  removed: "删除场次",
  changed: "场次有变化",
  unchanged: "没有变化",
};

const CHANGE_LABELS: Record<ScriptLineChange["change_type"], string> = {
  added: "新增台词",
  removed: "删除台词",
  modified: "修改台词",
};

export default function VersionTracking() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [previousScriptId, setPreviousScriptId] = useState("");
  const [currentScriptId, setCurrentScriptId] = useState("");
  const [diff, setDiff] = useState<ScriptVersionDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [filter, setFilter] = useState<SceneDiff["status"] | "all">("all");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const visibleScenes = useMemo(
    () => diff?.scenes.filter((scene) => filter === "all" || scene.status === filter) || [],
    [diff, filter],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getScripts()
      .then((items) => {
        if (cancelled) return;
        setScripts(items);
        if (items.length >= 2) {
          setCurrentScriptId(items[0].script_id);
          setPreviousScriptId(items[1].script_id);
        }
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本版本加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function compare() {
    if (!previousScriptId || !currentScriptId) {
      setError("请先选择两个剧本版本");
      return;
    }
    setComparing(true);
    setError("");
    setMessage("");
    try {
      setDiff(await compareScriptVersions(currentScriptId, previousScriptId));
      setMessage("版本差异已计算，所有变更均回指保存的场次和台词证据。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "剧本版本比较失败");
    } finally {
      setComparing(false);
    }
  }

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <GitBranch className="text-primary" size={30} />
            版本追踪
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            比较两个剧本版本的场次、角色、道具和台词变化，快速定位排练计划需要重新核对的地方。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          版本差异 Agent
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

      <Card>
        <CardContent className="p-4 md:p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end">
            <VersionSelect
              label="基准版本（旧）"
              value={previousScriptId}
              scripts={scripts}
              onChange={(value) => {
                setPreviousScriptId(value);
                setDiff(null);
                setMessage("");
              }}
            />
            <div className="hidden pb-2 text-dim xl:block"><ArrowRight size={18} /></div>
            <VersionSelect
              label="目标版本（新）"
              value={currentScriptId}
              scripts={scripts}
              onChange={(value) => {
                setCurrentScriptId(value);
                setDiff(null);
                setMessage("");
              }}
            />
            <Button type="button" className="shrink-0" onClick={() => void compare()} disabled={loading || comparing || scripts.length < 2}>
              {comparing ? <Loader2 className="animate-spin" /> : <GitBranch size={14} />}
              比较两个版本
            </Button>
          </div>
          {scripts.length < 2 && !loading && (
            <div className="mt-4 flex flex-col gap-3 rounded-xl border border-border bg-background/40 px-3 py-3 text-sm text-dim sm:flex-row sm:items-center sm:justify-between">
              <span>至少保存两个剧本版本后，才能进行差异比较。</span>
              <Button type="button" variant="outline" size="sm" onClick={() => navigate("/rehearsal")}>
                去解析新版本
                <ArrowRight size={14} />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {!diff ? (
        <Card className="min-h-[540px]">
          <CardContent className="flex min-h-[540px] flex-col items-center justify-center p-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary">
              <FileText size={29} />
            </div>
            <div className="mt-5 text-xl font-semibold">等待一次版本比较</div>
            <p className="mt-2 max-w-lg text-sm leading-6 text-dim">
              Agent 会优先按场次编号对齐，再比较角色、道具和台词；新增、删除和修改都会保留来源行号。
            </p>
          </CardContent>
        </Card>
      ) : (
        <DiffResult diff={diff} filter={filter} setFilter={setFilter} visibleScenes={visibleScenes} />
      )}
    </div>
  );
}

function VersionSelect({
  label,
  value,
  scripts,
  onChange,
}: {
  label: string;
  value: string;
  scripts: ScriptSummary[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block min-w-0 flex-1">
      <span className="text-xs font-medium text-text">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1.5 flex h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
        aria-label={label}
      >
        <option value="">选择剧本版本</option>
        {scripts.map((script) => (
          <option key={script.script_id} value={script.script_id}>
            {script.title} · {script.version_label} · {script.created_at.slice(0, 10)}
          </option>
        ))}
      </select>
    </label>
  );
}

function DiffResult({
  diff,
  filter,
  setFilter,
  visibleScenes,
}: {
  diff: ScriptVersionDiff;
  filter: SceneDiff["status"] | "all";
  setFilter: (value: SceneDiff["status"] | "all") => void;
  visibleScenes: SceneDiff[];
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 md:p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2 text-lg font-semibold">
                {diff.previous_title}
                <span className="text-dim">·</span>
                <span className="text-dim">{diff.previous_version_label}</span>
                <ArrowRight size={16} className="text-primary" />
                <span>{diff.current_version_label}</span>
              </div>
              <p className="mt-1 text-sm leading-6 text-dim">{diff.summary}</p>
            </div>
            <span className="rounded-full border border-teal/25 bg-teal/8 px-2.5 py-1 text-[11px] text-teal">确定性证据比较</span>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="新增场次" value={diff.added_scene_count} tone="green" />
            <Metric label="删除场次" value={diff.removed_scene_count} tone="red" />
            <Metric label="修改场次" value={diff.changed_scene_count} tone="orange" />
            <Metric label="无变化" value={diff.unchanged_scene_count} tone="teal" />
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold">场次变更明细</div>
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as SceneDiff["status"] | "all")}
          className="h-9 rounded-lg border border-border bg-input px-3 text-xs text-text outline-none focus:border-accent"
          aria-label="筛选场次变化"
        >
          <option value="all">全部场次</option>
          <option value="changed">只看修改</option>
          <option value="added">只看新增</option>
          <option value="removed">只看删除</option>
          <option value="unchanged">只看无变化</option>
        </select>
      </div>

      {visibleScenes.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-dim">当前筛选没有对应的场次。</CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {visibleScenes.map((scene) => <SceneDiffCard key={scene.scene_key} scene={scene} />)}
        </div>
      )}
    </div>
  );
}

function SceneDiffCard({ scene }: { scene: SceneDiff }) {
  const statusStyles = {
    added: "border-green/25 bg-green/6 text-green",
    removed: "border-red/25 bg-red/6 text-red",
    changed: "border-orange/25 bg-orange/6 text-orange",
    unchanged: "border-border bg-background/35 text-dim",
  };
  return (
    <article className={cn("rounded-xl border p-4", statusStyles[scene.status])}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">第 {scene.scene_number} 场</div>
          <div className="mt-1 text-xs text-text">
            {scene.status === "removed" ? scene.old_title : scene.new_title || scene.old_title}
            {scene.status === "changed" && scene.old_title !== scene.new_title && (
              <span className="ml-2 text-dim">原：{scene.old_title}</span>
            )}
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-current/20 px-2 py-0.5 text-[10px]">{STATUS_LABELS[scene.status]}</span>
      </div>

      <div className="mt-3 text-xs leading-5 text-text">{scene.summary}</div>
      {scene.impact.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {scene.impact.map((item) => <span key={item} className="rounded-full bg-card/70 px-2 py-1 text-[10px] text-dim">{item}</span>)}
        </div>
      )}

      {(scene.added_characters.length > 0 || scene.removed_characters.length > 0) && (
        <ChangeRow icon={<Users size={13} />} label="角色" added={scene.added_characters} removed={scene.removed_characters} />
      )}
      {(scene.added_props.length > 0 || scene.removed_props.length > 0) && (
        <ChangeRow icon={<Package size={13} />} label="道具" added={scene.added_props} removed={scene.removed_props} />
      )}

      {scene.line_changes.length > 0 && (
        <div className="mt-3 space-y-2 border-t border-current/10 pt-3">
          <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.14em] text-dim">
            <PencilLine size={13} /> 台词变化
          </div>
          {scene.line_changes.map((change, index) => <LineChangeRow key={`${change.change_type}-${change.character}-${index}`} change={change} />)}
        </div>
      )}
    </article>
  );
}

function ChangeRow({
  icon,
  label,
  added,
  removed,
}: {
  icon: ReactNode;
  label: string;
  added: string[];
  removed: string[];
}) {
  return (
    <div className="mt-3 flex items-start gap-2 border-t border-current/10 pt-3 text-xs">
      <span className="mt-0.5 text-dim">{icon}</span>
      <span className="shrink-0 text-dim">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {added.map((item) => <span key={`add-${item}`} className="rounded-full bg-green/10 px-2 py-0.5 text-green">+ {item}</span>)}
        {removed.map((item) => <span key={`remove-${item}`} className="rounded-full bg-red/10 px-2 py-0.5 text-red">− {item}</span>)}
      </div>
    </div>
  );
}

function LineChangeRow({ change }: { change: ScriptLineChange }) {
  const styles = {
    added: "border-green/20 bg-green/6",
    removed: "border-red/20 bg-red/6",
    modified: "border-orange/20 bg-orange/6",
  };
  const icons = {
    added: <Plus size={12} className="text-green" />,
    removed: <Minus size={12} className="text-red" />,
    modified: <PencilLine size={12} className="text-orange" />,
  };
  return (
    <div className={cn("rounded-lg border px-2.5 py-2 text-[11px] leading-5", styles[change.change_type])}>
      <div className="flex items-center gap-1.5 font-medium text-text">
        {icons[change.change_type]}
        {change.character} · {CHANGE_LABELS[change.change_type]}
      </div>
      {change.old_text && <div className="mt-1 text-red/85">旧：{change.old_text} <span className="text-dim">（第 {change.old_source_line} 行）</span></div>}
      {change.new_text && <div className="mt-1 text-green/85">新：{change.new_text} <span className="text-dim">（第 {change.new_source_line} 行）</span></div>}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: "green" | "red" | "orange" | "teal" }) {
  const tones = {
    green: "bg-green/10 text-green",
    red: "bg-red/10 text-red",
    orange: "bg-orange/10 text-orange",
    teal: "bg-teal/10 text-teal",
  };
  return (
    <div className={cn("rounded-xl px-3 py-2.5", tones[tone])}>
      <div className="text-[11px] opacity-80">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
