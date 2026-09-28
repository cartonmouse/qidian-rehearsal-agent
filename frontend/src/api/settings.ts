import { API_BASE, authFetch } from "./client";

export async function getSettings() {
  const response = await authFetch(`${API_BASE}/settings`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function updateSettings(payload: Record<string, unknown>) {
  const response = await authFetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function testLLMConnection(payload: Record<string, unknown>) {
  const response = await authFetch(`${API_BASE}/settings/test-llm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function testEmbeddingConnection(payload: Record<string, unknown>) {
  const response = await authFetch(`${API_BASE}/settings/test-embedding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
