import { useEffect, useMemo, useState, type DragEvent, type FormEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CircleDot,
  Check,
  Eye,
  EyeOff,
  GripVertical,
  ListOrdered,
  Loader2,
  LogIn,
  LogOut,
  Map,
  MessageSquareText,
  Move,
  Plus,
  Package,
  Pencil,
  RotateCcw,
  Save,
  Trash2,
  Theater,
  Users,
} from "lucide-react";

import {
  getScript,
  getScripts,
  getStageTagCatalog,
  getStageVisualization,
  resetStageVisualization,
  saveStageVisualization,
  type ScriptAnalysis,
  type ScriptSummary,
  type StageActor,
  type StageEvent,
  type StagePosition,
  type StageTagCatalog,
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

function normalizeStageLabel(value: string): string {
  return value.trim();
}

function sameStageLabel(left: string, right: string): boolean {
  return normalizeStageLabel(left).toLocaleLowerCase() === normalizeStageLabel(right).toLocaleLowerCase();
}

export default function StageVisualization() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState("");
  const [analysis, setAnalysis] = useState<ScriptAnalysis | null>(null);
  const [sceneId, setSceneId] = useState("");
  const [view, setView] = useState<StageView | null>(null);
  const [draftActors, setDraftActors] = useState<StageActor[]>([]);
  const [draftProps, setDraftProps] = useState<StageProp[]>([]);
  const [stageTags, setStageTags] = useState<StageTagCatalog>({ actors: [], props: [] });
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedScene = useMemo(
    () => analysis?.scenes.find((scene) => scene.scene_id === sceneId) || null,
    [analysis, sceneId],
  );

  const reusableActorNames = useMemo(() => Array.from(new Set([
    ...(analysis?.characters || []).map((character) => character.name),
    ...stageTags.actors.map((tag) => tag.name),
  ])).filter(Boolean).sort((left, right) => left.localeCompare(right, "zh-CN")), [analysis, stageTags]);

  const reusablePropNames = useMemo(() => Array.from(new Set([
    ...(analysis?.props || []).map((prop) => prop.name),
    ...stageTags.props.map((tag) => tag.name),
  ])).filter(Boolean).sort((left, right) => left.localeCompare(right, "zh-CN")), [analysis, stageTags]);

  useEffect(() => {
    if (!view) return;
    setDraftActors(view.actors.map((actor) => ({ ...actor, source_lines: [...actor.source_lines] })));
    setDraftProps(view.props.map((prop) => ({ ...prop, source_lines: [...prop.source_lines] })));
    setEditing(false);
  }, [view]);

  useEffect(() => {
    let cancelled = false;
    void getStageTagCatalog()
      .then((catalog) => {
        if (!cancelled) setStageTags(catalog);
      })
      .catch(() => {
        // The catalog is an enhancement; the current script's Agent labels
        // remain available even when the optional catalog request fails.
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const addActorLabel = (rawName: string): boolean => {
    const name = normalizeStageLabel(rawName);
    if (!name) {
      setError("人物标签不能为空");
      return false;
    }
    if (draftActors.some((actor) => sameStageLabel(actor.name, name))) {
      setError(`本场已经有“${name}”这个人物标签`);
      return false;
    }
    setDraftActors((items) => [
      ...items,
      { name, status: "unknown", position: "unknown", source_lines: [], origin: "manual", visible: true },
    ]);
    setError("");
    return true;
  };

  const addPropLabel = (rawName: string): boolean => {
    const name = normalizeStageLabel(rawName);
    if (!name) {
      setError("道具标签不能为空");
      return false;
    }
    if (draftProps.some((prop) => sameStageLabel(prop.name, name))) {
      setError(`本场已经有“${name}”这个道具标签`);
      return false;
    }
    setDraftProps((items) => [
      ...items,
      { name, position: "unknown", source_lines: [], origin: "manual", visible: true },
    ]);
    setError("");
    return true;
  };

  const renameActorLabel = (oldName: string, rawName: string): boolean => {
    const name = normalizeStageLabel(rawName);
    if (!name) {
      setError("人物标签不能为空");
      return false;
    }
    if (draftActors.some((actor) => !sameStageLabel(actor.name, oldName) && sameStageLabel(actor.name, name))) {
      setError(`本场已经有“${name}”这个人物标签`);
      return false;
    }
    setDraftActors((items) => items.map((actor) => (
      sameStageLabel(actor.name, oldName)
        ? { ...actor, name, origin: "manual", source_lines: [] }
        : actor
    )));
    setError("");
    return true;
  };

  const renamePropLabel = (oldName: string, rawName: string): boolean => {
    const name = normalizeStageLabel(rawName);
    if (!name) {
      setError("道具标签不能为空");
      return false;
    }
    if (draftProps.some((prop) => !sameStageLabel(prop.name, oldName) && sameStageLabel(prop.name, name))) {
      setError(`本场已经有“${name}”这个道具标签`);
      return false;
    }
    setDraftProps((items) => items.map((prop) => (
      sameStageLabel(prop.name, oldName)
        ? { ...prop, name, origin: "manual", source_lines: [] }
        : prop
    )));
    setError("");
    return true;
  };

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
                  setDraftActors([]);
                  setDraftProps([]);
                  setEditing(false);
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
                  setDraftActors([]);
                  setDraftProps([]);
                  setEditing(false);
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
        <div className="space-y-4">
          <StageEditorToolbar
            view={view}
            editing={editing}
            saving={saving}
            onToggleEditing={() => {
              if (editing) {
                setDraftActors(view.actors.map((actor) => ({ ...actor, source_lines: [...actor.source_lines] })));
                setDraftProps(view.props.map((prop) => ({ ...prop, source_lines: [...prop.source_lines] })));
              }
              setEditing((current) => !current);
            }}
            onSave={async () => {
              setSaving(true);
              setError("");
              try {
                const saved = await saveStageVisualization(selectedScriptId, sceneId, {
                  actors: draftActors,
                  props: draftProps,
                  replace_lists: true,
                });
                setView(saved);
                void getStageTagCatalog().then(setStageTags).catch(() => undefined);
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "舞台布局保存失败");
              } finally {
                setSaving(false);
              }
            }}
            onReset={async () => {
              setSaving(true);
              setError("");
              try {
                const restored = await resetStageVisualization(selectedScriptId, sceneId);
                setView(restored);
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "恢复 Agent 舞台布局失败");
              } finally {
                setSaving(false);
              }
            }}
          />
          {editing && (
            <StageTagEditor
              actors={draftActors}
              props={draftProps}
              actorOptions={reusableActorNames}
              propOptions={reusablePropNames}
              onAddActor={addActorLabel}
              onAddProp={addPropLabel}
              onRenameActor={renameActorLabel}
              onRenameProp={renamePropLabel}
              onRemoveActor={(name) => {
                setDraftActors((items) => items.filter((actor) => !sameStageLabel(actor.name, name)));
                setError("");
              }}
              onRemoveProp={(name) => {
                setDraftProps((items) => items.filter((prop) => !sameStageLabel(prop.name, name)));
                setError("");
              }}
            />
          )}
          <div className="grid gap-4 xl:grid-cols-[minmax(500px,1fr)_minmax(420px,0.82fr)]">
            <StageMap
              view={view}
              editing={editing}
              actors={draftActors}
              props={draftProps}
              onMoveActor={(name, position) => setDraftActors((items) => items.map((actor) => (
                actor.name === name ? { ...actor, position, visible: true } : actor
              )))}
              onMoveProp={(name, position) => setDraftProps((items) => items.map((prop) => (
                prop.name === name ? { ...prop, position, visible: true } : prop
              )))}
              onToggleActorStatus={(name) => setDraftActors((items) => items.map((actor) => (
                actor.name === name
                  ? { ...actor, status: actor.status === "onstage" ? "offstage" : actor.status === "offstage" ? "unknown" : "onstage" }
                  : actor
              )))}
              onToggleActorVisibility={(name) => setDraftActors((items) => items.map((actor) => (
                actor.name === name ? { ...actor, visible: !actor.visible } : actor
              )))}
              onTogglePropVisibility={(name) => setDraftProps((items) => items.map((prop) => (
                prop.name === name ? { ...prop, visible: !prop.visible } : prop
              )))}
            />
            <EventTimeline view={view} />
          </div>
        </div>
      )}
    </div>
  );
}

function StageEditorToolbar({
  view,
  editing,
  saving,
  onToggleEditing,
  onSave,
  onReset,
}: {
  view: StageView;
  editing: boolean;
  saving: boolean;
  onToggleEditing: () => void;
  onSave: () => void;
  onReset: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between md:p-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            <span>导演布局</span>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[10px]",
              view.human_overrides_applied ? "bg-teal/10 text-teal" : "bg-primary/10 text-primary",
            )}>
              {view.human_overrides_applied ? "已应用人工调整" : "Agent 建议"}
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-dim">
            {editing
              ? "拖动角色或道具到目标区域；点击角色可循环切换在场状态。保存后会作为本场导演布局。"
              : "Agent 布局仅供参考，导演可以进入编辑模式调整本场走位。"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={onToggleEditing} disabled={saving}>
            {editing ? <Check size={14} /> : <Pencil size={14} />}
            {editing ? "退出编辑" : "编辑布局"}
          </Button>
          <Button type="button" onClick={onSave} disabled={!editing || saving}>
            {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}
            保存导演布局
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={onReset}
            disabled={!view.human_overrides_applied || saving}
          >
            <RotateCcw size={14} />
            恢复 Agent 建议
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

type StageTagItem = {
  name: string;
  origin: "agent" | "manual";
};

function StageTagEditor({
  actors,
  props,
  actorOptions,
  propOptions,
  onAddActor,
  onAddProp,
  onRenameActor,
  onRenameProp,
  onRemoveActor,
  onRemoveProp,
}: {
  actors: StageTagItem[];
  props: StageTagItem[];
  actorOptions: string[];
  propOptions: string[];
  onAddActor: (name: string) => boolean;
  onAddProp: (name: string) => boolean;
  onRenameActor: (oldName: string, name: string) => boolean;
  onRenameProp: (oldName: string, name: string) => boolean;
  onRemoveActor: (name: string) => void;
  onRemoveProp: (name: string) => void;
}) {
  return (
    <Card className="border-primary/20 bg-primary/[0.03]">
      <CardContent className="p-4 md:p-5">
        <div className="flex flex-col gap-1 border-b border-border pb-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Pencil size={16} className="text-primary" />
            场次标签编辑
          </div>
          <p className="text-xs leading-5 text-dim">
            当前场次可以独立新增、改名或移除人物和道具；已有标签可以直接复用。保存后才会写入本场布局，原剧本内容不会被改写。
          </p>
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <StageTagSection
            kind="actor"
            title="人物标签"
            icon={<Users size={15} className="text-teal" />}
            items={actors}
            options={actorOptions}
            onAdd={onAddActor}
            onRename={onRenameActor}
            onRemove={onRemoveActor}
          />
          <StageTagSection
            kind="prop"
            title="道具标签"
            icon={<Package size={15} className="text-orange" />}
            items={props}
            options={propOptions}
            onAdd={onAddProp}
            onRename={onRenameProp}
            onRemove={onRemoveProp}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function StageTagSection({
  kind,
  title,
  icon,
  items,
  options,
  onAdd,
  onRename,
  onRemove,
}: {
  kind: "actor" | "prop";
  title: string;
  icon: ReactNode;
  items: StageTagItem[];
  options: string[];
  onAdd: (name: string) => boolean;
  onRename: (oldName: string, name: string) => boolean;
  onRemove: (name: string) => void;
}) {
  const [newName, setNewName] = useState("");
  const [reuseName, setReuseName] = useState("");
  const availableOptions = options.filter((option) => !items.some((item) => sameStageLabel(item.name, option)));

  const addNew = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (onAdd(newName)) setNewName("");
  };

  const reuse = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (reuseName && onAdd(reuseName)) setReuseName("");
  };

  return (
    <div className="rounded-xl border border-border bg-background/35 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          {icon}
          {title}
          <span className="rounded-full bg-background/70 px-2 py-0.5 text-[10px] text-dim">{items.length}</span>
        </div>
        <span className="text-[10px] text-dim">{kind === "actor" ? "角色/演员" : "本场物件"}</span>
      </div>
      <form className="mt-3 flex gap-2" onSubmit={addNew}>
        <input
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-input px-3 text-xs text-text outline-none placeholder:text-dim/70 focus:border-primary focus:ring-1 focus:ring-primary/25"
          placeholder={kind === "actor" ? "输入新人物标签" : "输入新道具标签"}
          aria-label={kind === "actor" ? "新建人物标签" : "新建道具标签"}
        />
        <Button type="submit" variant="outline" className="h-9 shrink-0 px-3" disabled={!newName.trim()}>
          <Plus size={14} />
          新建
        </Button>
      </form>
      <form className="mt-2 flex gap-2" onSubmit={reuse}>
        <select
          value={reuseName}
          onChange={(event) => setReuseName(event.target.value)}
          className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-input px-3 text-xs text-text outline-none focus:border-primary focus:ring-1 focus:ring-primary/25"
          aria-label={kind === "actor" ? "复用人物标签" : "复用道具标签"}
        >
          <option value="">从已有标签复用</option>
          {availableOptions.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
        <Button type="submit" variant="outline" className="h-9 shrink-0 px-3" disabled={!reuseName}>
          复用
        </Button>
      </form>
      <div className="mt-3 space-y-1.5">
        {items.map((item) => (
          <EditableStageTagRow key={item.name} item={item} onRename={onRename} onRemove={onRemove} />
        ))}
        {items.length === 0 && <div className="rounded-lg border border-dashed border-border px-3 py-3 text-center text-xs text-dim">本场还没有标签</div>}
      </div>
    </div>
  );
}

function EditableStageTagRow({
  item,
  onRename,
  onRemove,
}: {
  item: StageTagItem;
  onRename: (oldName: string, name: string) => boolean;
  onRemove: (name: string) => void;
}) {
  const [draftName, setDraftName] = useState(item.name);

  useEffect(() => setDraftName(item.name), [item.name]);

  const commit = () => {
    if (draftName === item.name) return;
    if (!onRename(item.name, draftName)) setDraftName(item.name);
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/80 bg-card/60 px-2 py-1.5">
      <input
        value={draftName}
        onChange={(event) => setDraftName(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
          if (event.key === "Escape") setDraftName(item.name);
        }}
        className="min-w-0 flex-1 bg-transparent text-xs text-text outline-none"
        aria-label={`编辑${item.name}标签`}
      />
      <span className={cn(
        "shrink-0 rounded-full px-1.5 py-0.5 text-[9px]",
        item.origin === "manual" ? "bg-primary/10 text-primary" : "bg-teal/10 text-teal",
      )}>
        {item.origin === "manual" ? "手动" : "剧本"}
      </span>
      <button
        type="button"
        className="rounded p-1 text-dim transition-colors hover:bg-red/10 hover:text-red"
        onClick={() => onRemove(item.name)}
        aria-label={`从本场移除${item.name}`}
        title="从本场标签移除"
      >
        <Trash2 size={13} />
      </button>
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

function StageMap({
  view,
  editing,
  actors,
  props,
  onMoveActor,
  onMoveProp,
  onToggleActorStatus,
  onToggleActorVisibility,
  onTogglePropVisibility,
}: {
  view: StageView;
  editing: boolean;
  actors: StageActor[];
  props: StageProp[];
  onMoveActor: (name: string, position: StagePosition) => void;
  onMoveProp: (name: string, position: StagePosition) => void;
  onToggleActorStatus: (name: string) => void;
  onToggleActorVisibility: (name: string) => void;
  onTogglePropVisibility: (name: string) => void;
}) {
  const allActors = editing ? actors : view.actors;
  const allProps = editing ? props : view.props;
  const displayedActors = allActors.filter((actor) => actor.visible !== false);
  const displayedProps = allProps.filter((prop) => prop.visible !== false);
  const hiddenActors = allActors.filter((actor) => actor.visible === false);
  const hiddenProps = allProps.filter((prop) => prop.visible === false);
  const unknownActors = displayedActors.filter((actor) => actor.position === "unknown");
  const unknownProps = displayedProps.filter((prop) => prop.position === "unknown");
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 md:p-5">
        <div className="flex items-start justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold"><Map size={19} className="text-primary" /> 调度地图</div>
            <p className="mt-1 text-xs leading-5 text-dim">
              {editing ? "拖放角色和道具到舞台区域；点击角色切换在场状态，使用眼睛按钮暂时隐藏对象。" : "角色位置来自舞台提示；没有明确走位时使用默认布局并保留提醒。"}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-1.5">
            <span className="rounded-full bg-teal/10 px-2.5 py-1 text-[10px] text-teal">{displayedActors.length} 名角色 · {displayedProps.length} 件道具</span>
            {(hiddenActors.length > 0 || hiddenProps.length > 0) && (
              <span className="rounded-full bg-orange/10 px-2.5 py-1 text-[10px] text-orange">
                暂时隐藏 {hiddenActors.length + hiddenProps.length} 项
              </span>
            )}
          </div>
        </div>

        <div className={cn(
          "relative mt-5 overflow-hidden rounded-2xl border border-primary/20 bg-[radial-gradient(circle_at_center,rgba(245,158,11,0.10),transparent_58%)] p-2",
          editing && "ring-1 ring-primary/20",
        )}>
          <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 text-[10px] uppercase tracking-[0.2em] text-dim/70">舞台后方</div>
          <div className="grid grid-cols-3 gap-2 pt-5">
            {POSITION_CELLS.map((cell) => (
              <PositionCell
                key={cell.key}
                position={cell.key}
                label={cell.label}
                actors={displayedActors}
                props={displayedProps}
                editing={editing}
                onDropItem={(type, name, nextPosition) => {
                  if (type === "actor") onMoveActor(name, nextPosition);
                  else onMoveProp(name, nextPosition);
                }}
                onToggleActorStatus={onToggleActorStatus}
                onToggleActorVisibility={onToggleActorVisibility}
                onTogglePropVisibility={onTogglePropVisibility}
              />
            ))}
          </div>
          {editing && (unknownActors.length > 0 || unknownProps.length > 0) && (
            <div className="mt-3 rounded-xl border border-orange/25 bg-orange/8 p-2.5">
              <div className="flex items-center gap-2 text-[10px] font-medium text-orange">
                <AlertTriangle size={13} />
                待安排到舞台的对象（拖入上方区域）
              </div>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {unknownActors.map((actor) => (
                  <ActorChip
                    key={actor.name}
                    actor={actor}
                    editing
                    onToggle={() => onToggleActorStatus(actor.name)}
                    onToggleVisibility={() => onToggleActorVisibility(actor.name)}
                  />
                ))}
                {unknownProps.map((prop) => (
                  <PropChip
                    key={prop.name}
                    prop={prop}
                    editing
                    onToggleVisibility={() => onTogglePropVisibility(prop.name)}
                  />
                ))}
              </div>
            </div>
          )}
          {editing && (hiddenActors.length > 0 || hiddenProps.length > 0) && (
            <div className="mt-3 rounded-xl border border-border bg-background/35 p-2.5">
              <div className="flex items-center gap-2 text-[10px] font-medium text-dim">
                <EyeOff size={13} />
                本场暂时隐藏（点击眼睛恢复，或拖回舞台区域）
              </div>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {hiddenActors.map((actor) => (
                  <ActorChip
                    key={actor.name}
                    actor={actor}
                    editing
                    onToggle={() => onToggleActorStatus(actor.name)}
                    onToggleVisibility={() => onToggleActorVisibility(actor.name)}
                  />
                ))}
                {hiddenProps.map((prop) => (
                  <PropChip
                    key={prop.name}
                    prop={prop}
                    editing
                    onToggleVisibility={() => onTogglePropVisibility(prop.name)}
                  />
                ))}
              </div>
            </div>
          )}
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
  editing,
  onDropItem,
  onToggleActorStatus,
  onToggleActorVisibility,
  onTogglePropVisibility,
}: {
  position: StagePosition;
  label: string;
  actors: StageActor[];
  props: StageProp[];
  editing: boolean;
  onDropItem: (type: "actor" | "prop", name: string, position: StagePosition) => void;
  onToggleActorStatus: (name: string) => void;
  onToggleActorVisibility: (name: string) => void;
  onTogglePropVisibility: (name: string) => void;
}) {
  const cellActors = actors.filter((actor) => actor.position === position);
  const cellProps = props.filter((prop) => prop.position === position);
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!editing) return;
    event.preventDefault();
    const payload = event.dataTransfer.getData("application/x-qidian-stage-item");
    if (!payload) return;
    try {
      const item = JSON.parse(payload) as { type?: "actor" | "prop"; name?: string };
      if ((item.type === "actor" || item.type === "prop") && item.name) {
        onDropItem(item.type, item.name, position);
      }
    } catch {
      // Ignore malformed drag payloads from outside this stage editor.
    }
  };
  return (
    <div
      className={cn(
        "min-h-[126px] rounded-xl border border-border/80 bg-card/55 p-2.5 transition-colors hover:border-primary/30",
        editing && "border-dashed border-primary/35 hover:border-primary",
      )}
      onDragOver={editing ? (event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } : undefined}
      onDrop={handleDrop}
    >
      <div className="text-[10px] text-dim">{label}</div>
      <div className="mt-2 space-y-1.5">
        {cellActors.map((actor) => (
          <ActorChip
            key={actor.name}
            actor={actor}
            editing={editing}
            onToggle={() => onToggleActorStatus(actor.name)}
            onToggleVisibility={() => onToggleActorVisibility(actor.name)}
          />
        ))}
        {cellProps.map((prop) => (
          <PropChip
            key={prop.name}
            prop={prop}
            editing={editing}
            onToggleVisibility={() => onTogglePropVisibility(prop.name)}
          />
        ))}
        {cellActors.length === 0 && cellProps.length === 0 && <div className="pt-4 text-center text-[10px] text-dim/45">空位</div>}
      </div>
    </div>
  );
}

function ActorChip({
  actor,
  editing,
  onToggle,
  onToggleVisibility,
}: {
  actor: StageActor;
  editing: boolean;
  onToggle: () => void;
  onToggleVisibility: () => void;
}) {
  const statusStyle = actor.status === "onstage"
    ? "border-teal/30 bg-teal/10 text-teal"
    : actor.status === "offstage"
      ? "border-red/25 bg-red/8 text-red/80"
      : "border-border bg-background/40 text-dim";
  const statusLabel = actor.status === "onstage" ? "在场" : actor.status === "offstage" ? "不在场" : "未确认";
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-2 py-1.5 text-xs",
        statusStyle,
        editing && "cursor-grab active:cursor-grabbing hover:ring-1 hover:ring-primary/40",
      )}
      draggable={editing}
      role={editing ? "button" : undefined}
      tabIndex={editing ? 0 : undefined}
      title={editing ? "拖动调整位置；点击切换在场状态" : `${statusLabel} · ${actor.position}`}
      onClick={editing ? onToggle : undefined}
      onKeyDown={editing ? (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      } : undefined}
      onDragStart={editing ? (event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData(
          "application/x-qidian-stage-item",
          JSON.stringify({ type: "actor", name: actor.name }),
        );
      } : undefined}
    >
      {editing && <GripVertical size={13} className="shrink-0 opacity-60" />}
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary">{actor.name.slice(0, 1)}</span>
      <span className="min-w-0 flex-1 truncate">{actor.name}</span>
      <span className="h-1.5 w-1.5 rounded-full bg-current" title={statusLabel} />
      {editing && (
        <button
          type="button"
          className="rounded p-0.5 text-current/70 transition-colors hover:bg-background/35 hover:text-current"
          aria-label={actor.visible ? `暂时隐藏${actor.name}` : `恢复${actor.name}`}
          title={actor.visible ? "暂时隐藏本场角色" : "恢复到本场布局"}
          onClick={(event) => {
            event.stopPropagation();
            onToggleVisibility();
          }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {actor.visible ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      )}
    </div>
  );
}

function PropChip({
  prop,
  editing,
  onToggleVisibility,
}: {
  prop: StageProp;
  editing: boolean;
  onToggleVisibility: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-lg border border-orange/25 bg-orange/8 px-2 py-1.5 text-[11px] text-orange",
        editing && "cursor-grab active:cursor-grabbing hover:ring-1 hover:ring-orange/40",
      )}
      draggable={editing}
      title={editing ? "拖动调整道具位置" : prop.position}
      onDragStart={editing ? (event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData(
          "application/x-qidian-stage-item",
          JSON.stringify({ type: "prop", name: prop.name }),
        );
      } : undefined}
    >
      {editing && <GripVertical size={13} className="shrink-0 opacity-60" />}
      <Package size={13} />
      <span className="truncate">{prop.name}</span>
      {editing && (
        <button
          type="button"
          className="ml-auto rounded p-0.5 text-current/70 transition-colors hover:bg-background/35 hover:text-current"
          aria-label={prop.visible ? `暂时隐藏${prop.name}` : `恢复${prop.name}`}
          title={prop.visible ? "暂时隐藏本场道具" : "恢复到本场布局"}
          onClick={onToggleVisibility}
        >
          {prop.visible ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      )}
    </div>
  );
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
