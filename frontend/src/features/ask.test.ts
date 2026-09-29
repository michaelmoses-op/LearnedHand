import { afterEach, expect, test, vi } from "vitest";
import { askDocument } from "./ask";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function sseBody(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(enc.encode(chunks[i]));
      i += 1;
    },
  });
}

test("askDocument parses SSE events", async () => {
  const tokens: string[] = [];
  const citations: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          sseBody([
            'event: status\ndata: {"stage":"retrieving"}\n\n',
            'event: sources\ndata: {"items":[{"index":1,"chunk_id":"c","section_id":"s","ordinal":0,"context_prefix":""}]}\n\n',
            'event: token\ndata: {"text":"Hello "}\n\n',
            'event: token\ndata: {"text":"world"}\n\n',
            'event: citations\ndata: {"items":[{"index":1,"chunk_id":"c","section_id":"s"}]}\n\n',
            'event: done\ndata: {"ok":true}\n\n',
          ]),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
    ),
  );

  await askDocument("doc-1", "What?", {
    onToken: (t) => tokens.push(t),
    onCitations: (c) => citations.push(...c),
  });

  expect(tokens.join("")).toBe("Hello world");
  expect(citations).toEqual([{ index: 1, chunk_id: "c", section_id: "s" }]);
});

test("askDocument surfaces JSON errors before the stream", async () => {
  let err: string | null = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json(
        { code: "document_not_ready", detail: "Document is not ready for questions" },
        { status: 409 },
      ),
    ),
  );
  await askDocument("doc-1", "What?", {
    onError: (_c, d) => {
      err = d;
    },
  });
  expect(err).toMatch(/not ready/i);
});
