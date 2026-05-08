import type {
  AIDoneEvent, AIMessage, AIPageContext, AIRole,
} from "../types";

const TOKEN_KEY = "cleo_token"; // matches the existing api/client.ts convention

interface ChatBody {
  messages: { role: AIRole; content: string }[];
  page_context: AIPageContext | null;
  route_at_open: string | null;
}

export interface AIStreamHandlers {
  onTextDelta(delta: string): void;
  onToolUseStart(part: { id: string; name: string; input: Record<string, unknown> }): void;
  onToolUseEnd(part: {
    id: string; ok: boolean; error?: string;
    row_count?: number; truncated?: boolean; elapsed_ms?: number;
  }): void;
  onDone(evt: AIDoneEvent): void;
  onError(message: string): void;
}

/** Convert AIMessage history to the on-the-wire { role, content } shape. */
function flattenMessage(m: AIMessage): { role: AIRole; content: string } {
  const text = m.parts
    .filter((p): p is { kind: "text"; text: string } => p.kind === "text")
    .map((p) => p.text)
    .join("");
  return { role: m.role, content: text };
}

export async function streamChat(
  history: AIMessage[],
  pageContext: AIPageContext | null,
  routeAtOpen: string | null,
  handlers: AIStreamHandlers,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY);
  const body: ChatBody = {
    messages: history.map(flattenMessage),
    page_context: pageContext,
    route_at_open: routeAtOpen,
  };
  const resp = await fetch("/api/ai/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok || !resp.body) {
    handlers.onError(`HTTP ${resp.status}`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // Parse complete SSE events. Each event is a block separated by \n\n.
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = block.split("\n");
      let event = "message";
      const dataParts: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataParts.push(line.slice(6));
      }
      if (!dataParts.length) continue;
      let payload: any;
      try {
        payload = JSON.parse(dataParts.join("\n"));
      } catch {
        continue;
      }
      switch (event) {
        case "text_delta":
          handlers.onTextDelta(payload.delta);
          break;
        case "tool_use_start":
          handlers.onToolUseStart(payload);
          break;
        case "tool_use_end":
          handlers.onToolUseEnd(payload);
          break;
        case "done":
          handlers.onDone(payload);
          break;
        case "error":
          handlers.onError(payload.message ?? "unknown error");
          break;
      }
    }
  }
}
