// 带鉴权的 fetch 封装，供奇点排练 API 模块共用

export const API_BASE = "/api";

/** 保留一个轻量兼容类型，避免业务 API 与生成的旧 OpenAPI 文件耦合。 */
export type ApiResponse<_Path extends string = string, _Method extends string = string> = unknown;

function authHeaders(extra: HeadersInit = {}): Record<string, string> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = { ...(extra as Record<string, string>) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = authHeaders(options.headers);
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return res;
}

/** SSE 流式响应逐行解析:data: {json} 格式,每解析出一条调用 onEvent */
export async function consumeSSE(
  res: Response,
  onEvent: (data: Record<string, unknown>) => boolean | void
): Promise<void> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // keep incomplete line

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (onEvent(data) === true) return; // 返回 true 表示流结束
      } catch {
        /* ignore malformed lines */
      }
    }
  }
}
