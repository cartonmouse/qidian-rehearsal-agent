import { authFetch } from "./client";

export interface SourceSpan {
  start_line: number;
  end_line: number;
  excerpt: string;
}

export interface DialogueLine {
  line_id: string;
  character: string;
  text: string;
  source: SourceSpan;
}

export interface Scene {
  scene_id: string;
  number: number;
  title: string;
  characters: string[];
  props: string[];
  lines: DialogueLine[];
  stage_directions: StageDirection[];
  source: SourceSpan;
}

export interface StageDirection {
  text: string;
  kind: "entrance" | "exit" | "movement" | "prop" | "other";
  source_line: number;
}

export interface CharacterSummary {
  name: string;
  scene_ids: string[];
  dialogue_count: number;
}

export interface PropSummary {
  name: string;
  scene_ids: string[];
  mention_count: number;
}

export interface AgentStep {
  name: string;
  status: "completed" | "repaired" | "failed";
  summary: string;
  output_count: number;
}

export interface AgentRunRecord {
  run_id: string;
  parent_run_id: string | null;
  root_run_id: string | null;
  agent: "script-analysis" | "schedule-draft" | "schedule-plan" | "line-reading" | "script-rag" | "resource-check";
  action: string;
  script_id: string | null;
  script_title: string;
  mode: string;
  status: "completed" | "fallback" | "failed";
  summary: string;
  trace: AgentStep[];
  warnings: string[];
  duration_ms: number;
  created_at: string;
}

export interface AgentRunMetricItem {
  agent: string;
  run_count: number;
  completed_count: number;
  fallback_count: number;
  failed_count: number;
  failure_rate: number;
  fallback_rate: number;
  average_duration_ms: number;
}

export interface AgentFailureStep {
  name: string;
  failed_count: number;
  last_summary: string;
}

export interface AgentRunMetricsResponse {
  window_days: number;
  from_datetime: string;
  to_datetime: string;
  total_runs: number;
  completed_runs: number;
  fallback_runs: number;
  failed_runs: number;
  failure_rate: number;
  fallback_rate: number;
  average_duration_ms: number;
  by_agent: AgentRunMetricItem[];
  failed_steps: AgentFailureStep[];
  note: string;
  generated_at: string;
}

export interface ScriptAnalysis {
  script_id: string;
  title: string;
  version_label: string;
  analysis_mode: "deterministic" | "llm" | "hybrid";
  parser_version: string;
  review_status: "pending" | "confirmed" | "edited";
  reviewed_at: string | null;
  review_note: string;
  scenes: Scene[];
  characters: CharacterSummary[];
  props: PropSummary[];
  warnings: string[];
  trace: AgentStep[];
  created_at: string;
}

export interface ScriptSummary {
  script_id: string;
  title: string;
  version_label: string;
  scene_count: number;
  character_count: number;
  prop_count: number;
  review_status: "pending" | "confirmed" | "edited";
  created_at: string;
}

export interface ScriptRagEvidence {
  evidence_id: string;
  scene_id: string;
  scene_number: number;
  scene_title: string;
  source_type: "scene_context" | "dialogue" | "stage_direction";
  character: string;
  text: string;
  source_line: number;
  score: number;
  match_reason: string;
}

export interface ScriptRagResponse {
  script_id: string;
  script_title: string;
  question: string;
  answer: string;
  evidence: ScriptRagEvidence[];
  engine: "rules" | "llm" | "fallback";
  retrieval_engine: "rules" | "semantic" | "rules-fallback";
  note: string;
  created_at: string;
}

export interface ScriptLineChange {
  change_type: "added" | "removed" | "modified";
  character: string;
  old_text: string;
  new_text: string;
  old_source_line: number | null;
  new_source_line: number | null;
}

export interface SceneDiff {
  scene_key: string;
  scene_number: number;
  status: "added" | "removed" | "changed" | "unchanged";
  old_scene_id: string | null;
  new_scene_id: string | null;
  old_title: string;
  new_title: string;
  added_characters: string[];
  removed_characters: string[];
  added_props: string[];
  removed_props: string[];
  line_changes: ScriptLineChange[];
  impact: string[];
  summary: string;
}

export interface VersionDownstreamImpact {
  impact_type: "schedule" | "line-reading" | "resource";
  severity: "high" | "medium" | "info";
  scene_key: string;
  scene_number: number;
  scene_title: string;
  affected_characters: string[];
  affected_props: string[];
  resource_audit_matches: VersionResourceAuditMatch[];
  reason: string;
  action: string;
}

export interface VersionResourceAuditMatch {
  audit_id: string;
  resource_type: "inventory" | "room" | "music" | "budget" | "invoice";
  change_type: "created" | "updated" | "deleted";
  resource_id: string;
  label: string;
  summary: string;
  created_at: string;
}

export interface ScriptVersionDiff {
  previous_script_id: string;
  current_script_id: string;
  previous_version_label: string;
  current_version_label: string;
  previous_title: string;
  current_title: string;
  added_scene_count: number;
  removed_scene_count: number;
  changed_scene_count: number;
  unchanged_scene_count: number;
  scenes: SceneDiff[];
  summary: string;
  downstream_impacts: VersionDownstreamImpact[];
  requires_schedule_review: boolean;
  requires_line_reading_review: boolean;
  requires_resource_review: boolean;
}

export type StagePosition =
  | "upstage_left"
  | "upstage_center"
  | "upstage_right"
  | "center_left"
  | "center"
  | "center_right"
  | "downstage_left"
  | "downstage_center"
  | "downstage_right"
  | "unknown";

export interface StageActor {
  name: string;
  status: "onstage" | "offstage" | "unknown";
  position: StagePosition;
  source_lines: number[];
}

export interface StageProp {
  name: string;
  position: StagePosition;
  source_lines: number[];
}

export interface StageEvent {
  order: number;
  event_type: "entrance" | "exit" | "movement" | "prop" | "dialogue" | "other";
  subject: string;
  text: string;
  source_line: number;
}

export interface StageVisualization {
  script_id: string;
  scene_id: string;
  scene_number: number;
  scene_title: string;
  actors: StageActor[];
  props: StageProp[];
  events: StageEvent[];
  summary: string;
  warnings: string[];
}

export interface SceneReviewPatch {
  scene_id: string;
  title: string;
  characters: string[];
  props: string[];
}

export interface ScheduleTask {
  task_id: string;
  scene_id: string;
  scene_number: number;
  title: string;
  required_characters: string[];
  props: string[];
  estimated_minutes: number;
  parallel_group: number;
  parallel_reason: string;
  conflict_priority: "none" | "low" | "medium" | "high";
  alternatives: ScheduleAlternative[];
  manual_override: ScheduleManualOverride | null;
  scheduled_date: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  unassigned_reason: string | null;
  status: "draft" | "scheduled" | "unassigned" | "overridden";
}

export interface ScheduleAlternative {
  alternative_id: string;
  kind: "shorten_duration" | "split_by_actor" | "request_availability";
  label: string;
  reason: string;
  affected_actors: string[];
  date: string | null;
  start: string | null;
  end: string | null;
  duration_minutes: number | null;
  priority: "low" | "medium" | "high";
  requires_human_approval: boolean;
}

export interface ScheduleManualOverride {
  date: string;
  start: string;
  end: string;
  room_name: string | null;
  note: string;
  created_at: string;
}

export interface ScheduleToolCall {
  call_id: string;
  tool_name: string;
  phase: "inspect" | "extract" | "group" | "assign" | "validate" | "override";
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  status: "completed" | "repaired" | "failed";
  summary: string;
}

export interface ScheduleDraft {
  script_id: string;
  review_status: "pending" | "confirmed" | "edited";
  is_preview: boolean;
  agent_run_id: string | null;
  parent_run_id: string | null;
  root_run_id: string | null;
  tasks: ScheduleTask[];
  tool_calls: ScheduleToolCall[];
  created_at: string;
}

export interface ScheduleBatchOverrideResponse {
  script_id: string;
  schedule: ScheduleDraft;
  confirmed_task_ids: string[];
  overridden_count: number;
  atomic: boolean;
}

export interface AvailabilitySlot {
  actor: string;
  date: string;
  start: string;
  end: string;
}

export interface ResourceInventoryItem {
  resource_id: string;
  category: "prop" | "costume";
  name: string;
  quantity: number;
  status: "available" | "maintenance" | "missing";
  location: string;
  notes: string;
}

export interface ResourceAuditChange {
  change_type: "created" | "updated" | "deleted";
  resource_id: string;
  label: string;
  changed_fields: string[];
  summary: string;
}

export interface ResourceAuditRecord {
  audit_id: string;
  resource_type: "inventory" | "room" | "music" | "budget" | "invoice";
  operation: "replace" | "create" | "delete";
  changed_count: number;
  changes: ResourceAuditChange[];
  summary: string;
  created_at: string;
}

export interface ResourceAuditFilters {
  limit?: number;
  resourceType?: ResourceAuditRecord["resource_type"];
  changeType?: ResourceAuditRecord["changes"][number]["change_type"];
  query?: string;
}

export interface RoomBooking {
  booking_id: string;
  room_name: string;
  date: string;
  start: string;
  end: string;
  purpose: string;
}

export interface MusicTimelineNote {
  note_id: string;
  track_name: string;
  scene_id: string | null;
  cue_type: "intro" | "cue" | "transition" | "outro" | "other";
  start_seconds: number;
  end_seconds: number | null;
  note: string;
}

export interface BudgetLineItem {
  budget_item_id: string;
  category: "prop" | "costume" | "music" | "room" | "transport" | "promotion" | "other";
  name: string;
  estimated_amount: number;
  actual_amount: number;
  status: "planned" | "committed" | "paid" | "cancelled";
  note: string;
}

export interface InvoiceRecord {
  invoice_id: string;
  invoice_no: string;
  supplier: string;
  invoice_date: string;
  category: BudgetLineItem["category"];
  amount: number;
  budget_item_id: string | null;
  status: "pending" | "verified" | "paid" | "rejected";
  note: string;
}

export interface BudgetCategorySummary {
  category: string;
  estimated_amount: number;
  actual_amount: number;
  invoice_amount: number;
}

export interface ResourceFinanceSummary {
  estimated_total: number;
  actual_total: number;
  invoice_total: number;
  verified_invoice_total: number;
  linked_invoice_total: number;
  unlinked_invoice_total: number;
  variance: number;
  categories: BudgetCategorySummary[];
  warnings: string[];
  note: string;
}

export interface ResourceRequirement {
  name: string;
  required_quantity: number;
  available_quantity: number;
  status: "ready" | "missing" | "maintenance";
  note: string;
}

export interface ResourceCheckResponse {
  script_id: string;
  scene_id: string | null;
  scene_title: string;
  requirements: ResourceRequirement[];
  ready_count: number;
  missing_count: number;
  summary: string;
  warnings: string[];
}

export interface LineReadingTurn {
  character: string;
  text: string;
  source_line: number;
}

export interface LineReadingTranscriptItem {
  kind: "partner" | "actor" | "feedback";
  character: string;
  text: string;
  source_line: number | null;
}

export type LineReadingTone = "natural" | "restrained" | "urgent" | "warm" | "cold" | "uncertain";

export interface LineReadingSession {
  session_id: string;
  script_id: string;
  scene_id: string;
  scene_title: string;
  character: string;
  mode: "strict" | "adaptive";
  role_tone: LineReadingTone;
  context_note: string;
  line_index: number;
  actor_prompt: LineReadingTurn | null;
  transcript: LineReadingTranscriptItem[];
  turn_count: number;
  engine_counts: Record<string, number>;
  finished: boolean;
  created_at: string;
  updated_at: string;
}

export interface LineReadingResponse {
  script_id: string;
  scene_id: string;
  scene_title: string;
  character: string;
  mode: "strict" | "adaptive";
  role_tone: LineReadingTone;
  context_note: string;
  engine: "strict" | "llm" | "fallback";
  next_line_index: number | null;
  assistant_turns: LineReadingTurn[];
  actor_prompt: LineReadingTurn | null;
  feedback: string;
  note: string;
  finished: boolean;
  session_id: string;
  transcript: LineReadingTranscriptItem[];
  turn_count: number;
}

export interface RehearsalFeedback {
  record_id: string;
  script_id: string | null;
  script_title: string;
  scene_id: string | null;
  scene_title: string;
  rehearsal_date: string;
  participants: string[];
  outputs: string[];
  notes: string;
  summary: string;
  strengths: string[];
  blockers: string[];
  next_actions: string[];
  engine: "rules" | "llm" | "fallback";
  note: string;
  created_at: string;
}

export interface RehearsalMetricItem {
  label: string;
  count: number;
}

export interface RehearsalMetricTrend {
  date: string;
  sessions: number;
  outputs: number;
  blockers: number;
  next_actions: number;
}

export interface RehearsalMetricRecentSession {
  record_id: string;
  rehearsal_date: string;
  script_title: string;
  scene_title: string;
  outputs_count: number;
  blockers_count: number;
  next_actions_count: number;
  engine: "rules" | "llm" | "fallback";
}

export interface RehearsalMetrics {
  window_days: number;
  from_date: string;
  to_date: string;
  session_count: number;
  output_count: number;
  strength_count: number;
  blocker_count: number;
  next_action_count: number;
  sessions_with_outputs: number;
  sessions_with_blockers: number;
  sessions_with_next_actions: number;
  unique_participant_count: number;
  average_participants: number;
  output_coverage: number;
  blocker_rate: number;
  next_action_rate: number;
  engine_counts: Record<string, number>;
  top_strengths: RehearsalMetricItem[];
  top_blockers: RehearsalMetricItem[];
  trend: RehearsalMetricTrend[];
  recent_sessions: RehearsalMetricRecentSession[];
  note: string;
  generated_at: string;
}

export interface RehearsalLog {
  log_id: string;
  script_id: string | null;
  script_title: string;
  scene_id: string | null;
  scene_title: string;
  rehearsal_date: string;
  author: string;
  category: "direction" | "actor" | "blocking" | "prop" | "sound" | "general";
  content: string;
  tags: string[];
  source_line: number | null;
  created_at: string;
}

export interface Suggestion {
  suggestion_id: string;
  script_id: string | null;
  script_title: string;
  scene_id: string | null;
  scene_title: string;
  actor_name: string;
  category: "performance" | "blocking" | "script" | "team" | "safety" | "other";
  content: string;
  priority: "normal" | "high";
  status: "new" | "reviewed" | "accepted" | "archived";
  response: string;
  created_at: string;
  updated_at: string;
}

export interface Motto {
  motto_id: string;
  script_id: string | null;
  script_title: string;
  scene_id: string | null;
  scene_title: string;
  text: string;
  author: string;
  source: string;
  theme: "performance" | "team" | "theatre" | "life" | "other";
  tags: string[];
  favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromoCopy {
  copy_id: string;
  script_id: string | null;
  work_title: string;
  audience: "audience" | "recruitment" | "media" | "festival";
  tone: "poetic" | "concise" | "warm" | "experimental";
  brief: string;
  headline: string;
  short_copy: string;
  long_copy: string;
  hashtags: string[];
  engine: "rules" | "llm" | "fallback";
  note: string;
  created_at: string;
}

async function ensureOk(response: Response, fallback = "剧本解析失败"): Promise<Response> {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : fallback;
  throw new Error(detail);
}

export async function parseScript(payload: {
  title: string;
  version_label: string;
  script_text: string;
  analysis_mode?: "auto" | "rules" | "llm";
}): Promise<ScriptAnalysis> {
  const response = await authFetch("/api/rehearsal/scripts/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response);
  return response.json();
}

export async function getAgentRuns(limit = 50): Promise<AgentRunRecord[]> {
  const response = await authFetch(`/api/rehearsal/agent-runs?limit=${limit}`);
  await ensureOk(response, "Agent 运行记录加载失败");
  return response.json();
}

export async function getAgentRunMetrics(windowDays = 30): Promise<AgentRunMetricsResponse> {
  const response = await authFetch(`/api/rehearsal/agent-runs/metrics?window_days=${windowDays}`);
  await ensureOk(response, "Agent 运行指标加载失败");
  return response.json();
}

export async function getAgentRun(runId: string): Promise<AgentRunRecord> {
  const response = await authFetch(`/api/rehearsal/agent-runs/${encodeURIComponent(runId)}`);
  await ensureOk(response, "Agent 运行记录加载失败");
  return response.json();
}

export async function parseScriptFile(file: File, versionLabel: string): Promise<ScriptAnalysis> {
  const body = new FormData();
  body.append("file", file);
  body.append("version_label", versionLabel);
  const response = await authFetch("/api/rehearsal/scripts/parse-file", {
    method: "POST",
    body,
  });
  await ensureOk(response);
  return response.json();
}

export async function getScripts(): Promise<ScriptSummary[]> {
  const response = await authFetch("/api/rehearsal/scripts");
  await ensureOk(response);
  const payload = await response.json() as { items?: ScriptSummary[] };
  return payload.items || [];
}

export async function getScript(scriptId: string): Promise<ScriptAnalysis> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}`);
  await ensureOk(response);
  return response.json();
}

export async function compareScriptVersions(
  currentScriptId: string,
  previousScriptId: string,
): Promise<ScriptVersionDiff> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(currentScriptId)}/diff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ compare_script_id: previousScriptId }),
  });
  await ensureOk(response, "剧本版本比较失败");
  return response.json();
}

export async function getStageVisualization(
  scriptId: string,
  sceneId: string,
): Promise<StageVisualization> {
  const response = await authFetch(
    `/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/stage/${encodeURIComponent(sceneId)}`,
  );
  await ensureOk(response, "舞台可视化加载失败");
  return response.json();
}

export async function reviewScript(
  scriptId: string,
  payload: {
    scenes: SceneReviewPatch[];
    review_status: "confirmed" | "edited";
    review_note?: string;
  },
): Promise<ScriptAnalysis> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/review`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response);
  return response.json();
}

export async function generateScheduleDraft(
  scriptId: string,
  defaultMinutes = 45,
  preview = false,
): Promise<ScheduleDraft> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/schedule/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_minutes: defaultMinutes, preview }),
  });
  await ensureOk(response);
  return response.json();
}

export async function getScheduleDraft(scriptId: string): Promise<ScheduleDraft | null> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/schedule`);
  if (response.status === 404) return null;
  await ensureOk(response);
  return response.json();
}

export async function planSchedule(
  scriptId: string,
  slots: AvailabilitySlot[],
): Promise<ScheduleDraft> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/schedule/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slots }),
  });
  await ensureOk(response);
  return response.json();
}

export async function overrideSchedule(
  scriptId: string,
  payload: { task_id: string; date: string; start: string; end: string; room_name?: string; note?: string },
): Promise<ScheduleDraft> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/schedule/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "人工覆盖排班失败");
  return response.json();
}

export async function confirmScheduleBatch(
  scriptId: string,
  overrides: Array<{ task_id: string; date: string; start: string; end: string; room_name?: string; note?: string }>,
): Promise<ScheduleBatchOverrideResponse> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/schedule/override-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  await ensureOk(response, "批量确认排班失败");
  return response.json();
}

export async function getAvailability(): Promise<AvailabilitySlot[]> {
  const response = await authFetch("/api/rehearsal/availability");
  await ensureOk(response);
  return response.json();
}

export async function saveAvailability(slots: AvailabilitySlot[]): Promise<AvailabilitySlot[]> {
  const response = await authFetch("/api/rehearsal/availability", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slots }),
  });
  await ensureOk(response);
  return response.json();
}

export async function getResourceInventory(): Promise<ResourceInventoryItem[]> {
  const response = await authFetch("/api/rehearsal/resources/inventory");
  await ensureOk(response, "资源库存加载失败");
  return response.json();
}

export async function saveResourceInventory(
  items: ResourceInventoryItem[],
): Promise<ResourceInventoryItem[]> {
  const response = await authFetch("/api/rehearsal/resources/inventory", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  await ensureOk(response, "资源库存保存失败");
  return response.json();
}

export async function getResourceAudits(limitOrFilters: number | ResourceAuditFilters = 50): Promise<ResourceAuditRecord[]> {
  const filters: ResourceAuditFilters = typeof limitOrFilters === "number"
    ? { limit: limitOrFilters }
    : limitOrFilters;
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit ?? 50));
  if (filters.resourceType) params.set("resource_type", filters.resourceType);
  if (filters.changeType) params.set("change_type", filters.changeType);
  if (filters.query?.trim()) params.set("query", filters.query.trim());
  const response = await authFetch(`/api/rehearsal/resources/audit?${params.toString()}`);
  await ensureOk(response, "资源变更记录加载失败");
  return response.json();
}

export async function getRoomBookings(): Promise<RoomBooking[]> {
  const response = await authFetch("/api/rehearsal/resources/rooms");
  await ensureOk(response, "排练室预约加载失败");
  return response.json();
}

export async function createRoomBooking(payload: Omit<RoomBooking, "booking_id">): Promise<RoomBooking> {
  const response = await authFetch("/api/rehearsal/resources/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "排练室预约失败");
  return response.json();
}

export async function deleteRoomBooking(bookingId: string): Promise<void> {
  const response = await authFetch(`/api/rehearsal/resources/rooms/${encodeURIComponent(bookingId)}`, {
    method: "DELETE",
  });
  await ensureOk(response, "排练室预约删除失败");
}

export async function getMusicTimeline(): Promise<MusicTimelineNote[]> {
  const response = await authFetch("/api/rehearsal/resources/music");
  await ensureOk(response, "配乐时间轴加载失败");
  return response.json();
}

export async function saveMusicTimeline(notes: MusicTimelineNote[]): Promise<MusicTimelineNote[]> {
  const response = await authFetch("/api/rehearsal/resources/music", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  await ensureOk(response, "配乐时间轴保存失败");
  return response.json();
}

export async function getBudgetItems(): Promise<BudgetLineItem[]> {
  const response = await authFetch("/api/rehearsal/resources/budget");
  await ensureOk(response, "预算加载失败");
  return response.json();
}

export async function saveBudgetItems(items: BudgetLineItem[]): Promise<BudgetLineItem[]> {
  const response = await authFetch("/api/rehearsal/resources/budget", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  await ensureOk(response, "预算保存失败");
  return response.json();
}

export async function getInvoices(): Promise<InvoiceRecord[]> {
  const response = await authFetch("/api/rehearsal/resources/invoices");
  await ensureOk(response, "发票加载失败");
  return response.json();
}

export async function saveInvoices(invoices: InvoiceRecord[]): Promise<InvoiceRecord[]> {
  const response = await authFetch("/api/rehearsal/resources/invoices", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoices }),
  });
  await ensureOk(response, "发票保存失败");
  return response.json();
}

export async function getResourceFinanceSummary(): Promise<ResourceFinanceSummary> {
  const response = await authFetch("/api/rehearsal/resources/finance-summary");
  await ensureOk(response, "预算汇总加载失败");
  return response.json();
}

export async function checkScriptResources(
  scriptId: string,
  sceneId?: string | null,
): Promise<ResourceCheckResponse> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/resources/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scene_id: sceneId || null }),
  });
  await ensureOk(response, "道具资源检查失败");
  return response.json();
}

export async function readLine(
  scriptId: string,
  payload: {
    scene_id: string;
    character: string;
    mode: "strict" | "adaptive";
    role_tone: LineReadingTone;
    context_note: string;
    line_index: number;
    user_text?: string;
    session_id?: string;
  },
): Promise<LineReadingResponse> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/line-reading`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response);
  return response.json();
}

export async function getLineReadingSession(scriptId: string, sessionId: string): Promise<LineReadingSession> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/line-reading/sessions/${encodeURIComponent(sessionId)}`);
  await ensureOk(response, "对词会话加载失败");
  return response.json();
}

export async function getRehearsalFeedback(): Promise<RehearsalFeedback[]> {
  const response = await authFetch("/api/rehearsal/feedback");
  await ensureOk(response, "排练反馈档案加载失败");
  return response.json();
}

export async function createRehearsalFeedback(payload: {
  script_id?: string | null;
  scene_id?: string | null;
  rehearsal_date: string;
  participants: string[];
  outputs: string[];
  notes: string;
  analysis_mode: "auto" | "rules" | "llm";
}): Promise<RehearsalFeedback> {
  const response = await authFetch("/api/rehearsal/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "排练反馈归档失败");
  return response.json();
}

export async function getRehearsalMetrics(days = 30): Promise<RehearsalMetrics> {
  const response = await authFetch(`/api/rehearsal/feedback/metrics?days=${days}`);
  await ensureOk(response, "排练度量加载失败");
  return response.json();
}

export async function getRehearsalLogs(): Promise<RehearsalLog[]> {
  const response = await authFetch("/api/rehearsal/logbook");
  await ensureOk(response, "场记档案加载失败");
  return response.json();
}

export async function createRehearsalLog(payload: {
  script_id?: string | null;
  scene_id?: string | null;
  rehearsal_date: string;
  author: string;
  category: RehearsalLog["category"];
  content: string;
  tags: string[];
  source_line?: number | null;
}): Promise<RehearsalLog> {
  const response = await authFetch("/api/rehearsal/logbook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "场记归档失败");
  return response.json();
}

export async function deleteRehearsalLog(logId: string): Promise<void> {
  const response = await authFetch(`/api/rehearsal/logbook/${encodeURIComponent(logId)}`, {
    method: "DELETE",
  });
  await ensureOk(response, "场记删除失败");
}

export async function getSuggestions(): Promise<Suggestion[]> {
  const response = await authFetch("/api/rehearsal/suggestions");
  await ensureOk(response, "建议收件箱加载失败");
  return response.json();
}

export async function createSuggestion(payload: {
  script_id?: string | null;
  scene_id?: string | null;
  actor_name: string;
  category: Suggestion["category"];
  content: string;
}): Promise<Suggestion> {
  const response = await authFetch("/api/rehearsal/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "建议提交失败");
  return response.json();
}

export async function updateSuggestion(
  suggestionId: string,
  payload: { status: Suggestion["status"]; response: string },
): Promise<Suggestion> {
  const response = await authFetch(`/api/rehearsal/suggestions/${encodeURIComponent(suggestionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "建议状态更新失败");
  return response.json();
}

export async function deleteSuggestion(suggestionId: string): Promise<void> {
  const response = await authFetch(`/api/rehearsal/suggestions/${encodeURIComponent(suggestionId)}`, {
    method: "DELETE",
  });
  await ensureOk(response, "建议删除失败");
}

export async function getMottos(): Promise<Motto[]> {
  const response = await authFetch("/api/rehearsal/knowledge/mottos");
  await ensureOk(response, "格言表加载失败");
  return response.json();
}

export async function createMotto(payload: {
  script_id?: string | null;
  scene_id?: string | null;
  text: string;
  author: string;
  source: string;
  theme: Motto["theme"];
  tags: string[];
}): Promise<Motto> {
  const response = await authFetch("/api/rehearsal/knowledge/mottos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "格言保存失败");
  return response.json();
}

export async function updateMotto(mottoId: string, favorite: boolean): Promise<Motto> {
  const response = await authFetch(`/api/rehearsal/knowledge/mottos/${encodeURIComponent(mottoId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorite }),
  });
  await ensureOk(response, "格言收藏状态更新失败");
  return response.json();
}

export async function deleteMotto(mottoId: string): Promise<void> {
  const response = await authFetch(`/api/rehearsal/knowledge/mottos/${encodeURIComponent(mottoId)}`, {
    method: "DELETE",
  });
  await ensureOk(response, "格言删除失败");
}

export async function getPromoCopies(): Promise<PromoCopy[]> {
  const response = await authFetch("/api/rehearsal/knowledge/promo");
  await ensureOk(response, "宣传文案历史加载失败");
  return response.json();
}

export async function generatePromoCopy(payload: {
  script_id?: string | null;
  work_title: string;
  audience: PromoCopy["audience"];
  tone: PromoCopy["tone"];
  brief: string;
  analysis_mode: "auto" | "rules" | "llm";
}): Promise<PromoCopy> {
  const response = await authFetch("/api/rehearsal/knowledge/promo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "宣传文案生成失败");
  return response.json();
}

export async function askScriptRag(
  scriptId: string,
  payload: {
    question: string;
    top_k: number;
    retrieval_mode: "rules" | "semantic";
    answer_mode: "auto" | "rules" | "llm";
  },
): Promise<ScriptRagResponse> {
  const response = await authFetch(`/api/rehearsal/scripts/${encodeURIComponent(scriptId)}/rag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response, "剧本问答失败");
  return response.json();
}
