/** POST+fetch SSE client for cited Q&A (EventSource cannot send CSRF headers). */

import { readCsrfToken, refreshSession } from "../api/client";

export type AskSource = {
  index: number;
  chunk_id: string;
  section_id: string;
  ordinal: number;
  context_prefix: string;
};

export type AskCitation = {
  index: number;
  chunk_id: string;
  section_id: string;
};

export type AskHandlers = {
  onStatus?: (stage: string) => void;
  onSources?: (items: AskSource[]) => void;
  onToken?: (text: string) => void;
  onCitations?: (items: AskCitation[]) => void;
  onDone?: () => void;
  onError?: (code: string, detail: string) => void;
};

function dispatch(event: string, data: Record<string, unknown>, h: AskHandlers): void {
  switch (event) {
    case "status":
      if (typeof data.stage === "string") h.onStatus?.(data.stage);
      break;
    case "sources":
      h.onSources?.((data.items as AskSource[]) ?? []);
      break;
    case "token":
      if (typeof data.text === "string") h.onToken?.(data.text);
      break;
    case "citations":
      h.onCitations?.((data.items as AskCitation[]) ?? []);
      break;
    case "done":
      h.onDone?.();
      break;
    case "error":
      h.onError?.(
        typeof data.code === "string" ? data.code : "ask_failed",
        typeof data.detail === "string" ? data.detail : "Ask failed",
      );
      break;
  }
}

async function readSse(res: Response, handlers: AskHandlers): Promise<void> {
  if (!res.body) throw new Error("No response body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let event = "message";
  let dataLines: string[] = [];

  const flush = () => {
    if (!dataLines.length) return;
    try {
      const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      dispatch(event, data, handlers);
    } catch {
      handlers.onError?.("bad_event", "Malformed SSE event");
    }
    event = "message";
    dataLines = [];
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      else if (line === "") flush();
    }
  }
  flush();
}

export async function askDocument(
  documentId: string,
  question: string,
  handlers: AskHandlers,
): Promise<void> {
  const url = `${window.location.origin}/api/v1/documents/${documentId}/ask`;
  const post = () =>
    fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCsrfToken() ?? "",
      },
      body: JSON.stringify({ question }),
    });

  let res = await post();
  if (res.status === 401 && (await refreshSession())) res = await post();
  if (!res.ok) {
    const problem = (await res.json().catch(() => null)) as {
      code?: string;
      detail?: string;
    } | null;
    handlers.onError?.(problem?.code ?? "ask_failed", problem?.detail ?? "Ask failed");
    return;
  }
  await readSse(res, handlers);
}
