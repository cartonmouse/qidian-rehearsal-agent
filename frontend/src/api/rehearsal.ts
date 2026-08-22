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
  source: SourceSpan;
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

export interface ScriptAnalysis {
  script_id: string;
  title: string;
  version_label: string;
  analysis_mode: "deterministic";
  parser_version: string;
  scenes: Scene[];
  characters: CharacterSummary[];
  props: PropSummary[];
  warnings: string[];
  trace: AgentStep[];
  created_at: string;
}

async function ensureOk(response: Response): Promise<Response> {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : "剧本解析失败";
  throw new Error(detail);
}

export async function parseScript(payload: {
  title: string;
  version_label: string;
  script_text: string;
}): Promise<ScriptAnalysis> {
  const response = await authFetch("/api/rehearsal/scripts/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await ensureOk(response);
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
