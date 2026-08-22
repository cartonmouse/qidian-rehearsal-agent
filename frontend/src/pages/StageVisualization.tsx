import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CircleDot,
  ListOrdered,
  Loader2,
  LogIn,
  LogOut,
  Map,
  MessageSquareText,
  Move,
  Package,
  Theater,
  Users,
} from "lucide-react";

import {
  getScript,
  getScripts,
  getStageVisualization,
  type ScriptAnalysis,
  type ScriptSummary,
  type StageActor,
  type StageEvent,
  type StagePosition,
  type StageProp,
  type StageVisualization as StageView,
} from "@/api/rehearsal";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useNavigate } from "react-router-dom";

const PAGE_CLASS = "flex-1 w-full max-w-[1800px] mx-auto px-4 py-5 md:px-7 md:py-6 xl:px-8";

const POSITION_CELLS: Array<{ key: StagePosition; label: string }> = [
  { key: "upstage_left", label: "舞台后·左" },
  { key: "upstage_center", label: "舞台后·中" },
  { key: "upstage_right", label: "舞台后·右" },
  { key: "center_left", label: "中央·左" },
  { key: "center", label: "舞台中央" },
  { key: "center_right", label: "中央·右" },
  { key: "downstage_left", label: "台口·左" },
  { key: "downstage_center", label: "台口·中" },
  { key: "downstage_right", label: "台口·右" },
];

const EVENT_LABELS: Record<StageEvent["event_type"], string> = {
  entrance: "上场",
  exit: "下场",
  movement: "走位",
  prop: "道具",
  dialogue: "台词",
  other: "舞台提示",
};

export default function StageVisualization() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [sceneId, setSceneId] = useState("");
  const [view, setView] = useState<StageView | null>(null);
  const [loading, setLoading] = useState(true);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedScene = useMemo(
    () => analysis?.scenes.find((scene) => scene.scene_id === sceneId) || null,
    [analysis, sceneId],
  );

  useEffect(() => {
    let cancelled = false;
    void getScripts()
      .then((items) => {
        if (cancelled) return;
        setScripts(items);
        setSelectedScriptId((current) => (
          current && items.some((item) => item.script_id === current)
            ? current
            : items[0]?.script_id || ""
        ));
        if (items.length > 0) setSceneLoading(true);
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
      return;
    }
    let cancelled = false;
    void getScript(selectedScriptId)
      .then((item) => {
        if (cancelled) return;
        setSceneLoading(true);
        setAnalysis(item);
        setSceneId(item.scenes[0]?.scene_id || "");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "剧本详情加载失败");
      })
      .finally(() => {
        if (!cancelled) setSceneLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedScriptId]);

  useEffect(() => {
    if (!selectedScriptId || !sceneId) {
      return;
    }
    let cancelled = false;
    void getStageVisualization(selectedScriptId, sceneId)
      .then((item) => {
        if (!cancelled) setView(item);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "舞台可视化加载失败");
      })
      .finally(() => {
        if (!cancelled) setSceneLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sceneId, selectedScriptId]);

  return (
    <div className={cn(PAGE_CLASS, "space-y-4")}>
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-3xl font-display font-bold tracking-tight md:text-[38px]">
            <Map className="text-primary" size={30} />
            舞台可视化
          </div>
          <p className="mt-1 text-sm leading-6 text-dim">
            让剧本里的角色、道具和舞台提示变成一张可以排练时核对的动态地图。
          </p>
        </div>
        <div className="rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5 text-xs text-primary">
          Stage Agent
        </div>
      </header>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red/25 bg-red/8 px-4 py-2.5 text-sm text-red">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      <Card>
        <CardContent className="p-4 md:p-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
            <label className="min-w-0 flex-1">
              <span className="text-xs font-medium text-text">选择剧本版本</span>
              <select
                value={selectedScriptId}
                onChange={(event) => {
                  setSelectedScriptId(event.target.value);
                  setSceneLoading(Boolean(event.target.value));
                  setAnalysis(null);
                  setSceneId("");
                  setView(null);
                  setError("");
                }}
                className="mt-1.5 flex h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                aria-label="选择剧本版本"
              >
                <option value="">选择剧本版本</option>
                {scripts.map((script) => (
                  <option key={script.script_id} value={script.script_id}>
                    {script.title} · {script.version_label}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-0 flex-1">
              <span className="text-xs font-medium text-text">选择场次</span>
              <select
                value={sceneId}
                onChange={(event) => {
                  setSceneId(event.target.value);
                  setSceneLoading(Boolean(event.target.value));
                  setView(null);
                  setError("");
                }}
                disabled={!analysis || sceneLoading}
                className="mt-1.5 flex h-10 w-full rounded-xl border border-border bg-input px-3 text-sm text-text outline-none disabled:opacity-50 focus:border-accent focus:ring-1 focus:ring-accent/30"
                aria-label="选择场次"
              >
                <option value="">选择场次</option>
                {analysis?.scenes.map((scene) => (
                  <option key={scene.scene_id} value={scene.scene_id}>
                    第 {scene.number} 场 · {scene.title}
                  </option>
                ))}
              </select>
            </label>
            <Button type="button" variant="outline" className="shrink-0" onClick={() => navigate("/rehearsal")}>
              回到排练工作台
              <ArrowRight size={14} />
            </Button>
          </div>
          {selectedScene && (
            <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-primary">第 {selectedScene.number} 场</span>
              <span className="rounded-full bg-teal/10 px-2.5 py-1 text-teal">{selectedScene.lines.length} 条台词</span>
              <span className="rounded-full bg-orange/10 px-2.5 py-1 text-orange">{selectedScene.stage_directions.length} 条舞台提示</span>
            </div>
          )}
        </CardContent>
      </Card>

      {!selectedScriptId && !loading ? (
        <EmptyState onNavigate={() => navigate("/rehearsal")} />
      ) : !view || sceneLoading ? (
        <Card className="min-h-[620px]">
          <CardContent className="flex min-h-[620px] flex-col items-center justify-center text-center">
            <Loader2 className="animate-spin text-primary" size={28} />
            <div className="mt-3 text-sm text-dim">正在生成舞台地图...</div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(500px,1fr)_minmax(420px,0.82fr)]">
          <StageMap view={view} />
          <EventTimeline view={view} />
        </div>
      )}
    </div>
  );
}

function EmptyState({ onNavigate }: { onNavigate: () => void }) {
  return (
    <Card className="min-h-[620px]">
      <CardContent className="flex min-h-[620px] flex-col items-center justify-center p-6 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/12 text-primary"><Theater size={29} /></div>
        <div className="mt-5 text-xl font-semibold">还没有可视化的剧本</div>
        <p className="mt-2 max-w-md text-sm leading-6 text-dim">先在排练工作台保存一个剧本解析结果，Stage Agent 才能读取场次证据。</p>
        <Button type="button" variant="outline" className="mt-5" onClick={onNavigate}>
          去解析剧本
          <ArrowRight size={14} />
        </Button>
      </CardContent>
    </Card>
  );
}

function StageMap({ view }: { view: StageView }) {
  const unknownActors = view.actors.filter((actor) => actor.position === "unknown");
  const unknownProps = view.props.filter((prop) => prop.position === "unknown");
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold"><Map size={19} className="text-primary" /> 调度地图</div>
            <p className="mt-1 text-xs leading-5 text-dim">角色位置来自舞台提示；没有明确走位时使用默认布局并保留提醒。</p>
          </div>
          <span className="rounded-full bg-teal/10 px-2.5 py-1 text-[10px] text-teal">{view.actors.length} 名角色 · {view.props.length} 件道具</span>
        </div>

        <div className="relative mt-5 overflow-hidden rounded-2xl border border-primary/20 bg-[radial-gradient(circle_at_center,rgba(245,158,11,0.10),transparent_58%)] p-2">
          <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 text-[10px] uppercase tracking-[0.2em] text-dim/70">舞台后方</div>
          <div className="grid grid-cols-3 gap-2 pt-5">
            {POSITION_CELLS.map((cell) => (
              <PositionCell key={cell.key} position={cell.key} label={cell.label} actors={view.actors} props={view.props} />
            ))}
          </div>
          <div className="pointer-events-none mt-2 flex justify-between px-2 text-[10px] uppercase tracking-[0.2em] text-dim/70">
            <span>左侧台口</span><span>观众方向 / 台口</span><span>右侧台口</span>
          </div>
        </div>

        {(unknownActors.length > 0 || unknownProps.length > 0) && (
          <div className="mt-4 rounded-xl border border-orange/25 bg-orange/8 px-3 py-2.5 text-xs leading-5 text-orange">
            <div className="font-medium">仍需人工确认位置</div>
            {unknownActors.length > 0 && <div className="mt-1">角色：{unknownActors.map((actor) => actor.name).join("、")}</div>}
            {unknownProps.length > 0 && <div className="mt-1">道具：{unknownProps.map((prop) => prop.name).join("、")}</div>}
          </div>
        )}

        {view.warnings.length > 0 && (
          <div className="mt-4 space-y-1.5 rounded-xl border border-border bg-background/35 px-3 py-2.5 text-xs leading-5 text-dim">
            {view.warnings.map((warning) => <div key={warning} className="flex items-start gap-1.5"><AlertTriangle size={13} className="mt-1 shrink-0 text-orange" />{warning}</div>)}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PositionCell({
  position,
  label,
  actors,
  props,
}: {
  position: StagePosition;
  label: string;
  actors: StageActor[];
  props: StageProp[];
}) {
  const cellActors = actors.filter((actor) => actor.position === position);
  const cellProps = props.filter((prop) => prop.position === position);
  return (
    <div className="min-h-[126px] rounded-xl border border-border/80 bg-card/55 p-2.5 transition-colors hover:border-primary/30">
      <div className="text-[10px] text-dim">{label}</div>
      <div className="mt-2 space-y-1.5">
        {cellActors.map((actor) => <ActorChip key={actor.name} actor={actor} />)}
        {cellProps.map((prop) => <PropChip key={prop.name} prop={prop} />)}
        {cellActors.length === 0 && cellProps.length === 0 && <div className="pt-4 text-center text-[10px] text-dim/45">空位</div>}
      </div>
    </div>
  );
}

function ActorChip({ actor }: { actor: StageActor }) {
  const statusStyle = actor.status === "onstage"
    ? "border-teal/30 bg-teal/10 text-teal"
    : actor.status === "offstage"
      ? "border-red/25 bg-red/8 text-red/80"
      : "border-border bg-background/40 text-dim";
  return (
    <div className={cn("flex items-center gap-2 rounded-lg border px-2 py-1.5 text-xs", statusStyle)}>
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary">{actor.name.slice(0, 1)}</span>
      <span className="min-w-0 flex-1 truncate">{actor.name}</span>
      <span className="h-1.5 w-1.5 rounded-full bg-current" title={actor.status} />
    </div>
  );
}

function PropChip({ prop }: { prop: StageProp }) {
  return <div className="flex items-center gap-1.5 rounded-lg border border-orange/25 bg-orange/8 px-2 py-1.5 text-[11px] text-orange"><Package size={13} /> <span className="truncate">{prop.name}</span></div>;
}

function EventTimeline({ view }: { view: StageView }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold"><ListOrdered size={19} className="text-primary" /> 上下场动态</div>
            <p className="mt-1 text-xs leading-5 text-dim">按照剧本原文行号排列，排练时可以从事件回看证据。</p>
          </div>
          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[10px] text-primary">{view.events.length} 个事件</span>
        </div>

        <div className="mt-4 max-h-[650px] space-y-2 overflow-y-auto pr-1">
          {view.events.length === 0 ? (
            <div className="rounded-xl border border-border bg-background/35 px-3 py-4 text-center text-sm text-dim">当前场次没有可展示的事件。</div>
          ) : view.events.map((event) => <EventRow key={`${event.order}-${event.source_line}`} event={event} />)}
        </div>
      </CardContent>
    </Card>
  );
}

function EventRow({ event }: { event: StageEvent }) {
  const icon = event.event_type === "entrance"
    ? <LogIn size={14} className="text-green" />
    : event.event_type === "exit"
      ? <LogOut size={14} className="text-red" />
      : event.event_type === "movement"
        ? <Move size={14} className="text-teal" />
        : event.event_type === "prop"
          ? <Package size={14} className="text-orange" />
          : event.event_type === "dialogue"
            ? <MessageSquareText size={14} className="text-primary" />
            : <CircleDot size={14} className="text-dim" />;
  return (
    <div className="flex gap-3 rounded-xl border border-border bg-background/35 px-3 py-2.5">
      <div className="flex w-6 shrink-0 flex-col items-center gap-1 pt-0.5">
        {icon}
        <span className="text-[10px] text-dim">{event.order}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
          <span>{EVENT_LABELS[event.event_type]}</span>
          <span className="text-dim">· {event.subject}</span>
          <span className="rounded-full bg-card px-1.5 py-0.5 text-[10px] font-normal text-dim">原文第 {event.source_line} 行</span>
        </div>
        <div className="mt-1 text-xs leading-5 text-dim">{event.text}</div>
      </div>
    </div>
  );
}
