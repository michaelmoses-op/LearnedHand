# 9. POST+fetch SSE for cited Q&A

Status: accepted

## Context

Cookie auth uses a double-submit CSRF header on state-changing requests
(ADR-0006). Browser `EventSource` only does GET and cannot attach custom
headers, so it cannot call an authenticated ask endpoint safely.

## Decision

`POST /api/v1/documents/{id}/ask` returns `text/event-stream`. Clients use
`fetch` + `ReadableStream` (with CSRF), not `EventSource`. Event names:
`status`, `sources`, `token`, `citations`, `done`, `error`.

Generation lives in `app/generation` (eval-callable). Citations in the answer
are verified against retrieved chunk ids before the `citations` event.
Model HTML is sanitized with `nh3`. Prompt file is human-owned baseline only.

## Consequences

- OpenAPI documents the route; the TS client may not model the stream body —
  the frontend uses a dedicated fetch helper.
- Ownership / readiness errors are JSON (404 / 409) before the stream starts
  so IDOR tests stay uniform.
