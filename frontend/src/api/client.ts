import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

const CSRF_COOKIES = ["__Host-csrf", "csrf"];
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

export function readCsrfToken(): string | undefined {
  for (const name of CSRF_COOKIES) {
    const hit = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
    if (hit) return decodeURIComponent(hit.slice(name.length + 1));
  }
  return undefined;
}

let refreshing: Promise<boolean> | null = null;

/** Single-flight refresh so parallel 401s trigger one rotation (rotation is single-use). */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${window.location.origin}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": readCsrfToken() ?? "" },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const csrf: Middleware = {
  onRequest({ request }) {
    if (!SAFE.has(request.method)) {
      const token = readCsrfToken();
      if (token) request.headers.set("X-CSRF-Token", token);
    }
    return request;
  },
};

const retryAfterRefresh: Middleware = {
  async onResponse({ request, response }) {
    const path = new URL(request.url).pathname;
    if (response.status !== 401 || path.startsWith("/api/v1/auth/")) return response;
    if (!(await refreshSession())) return response;
    const retry = new Request(request.url, {
      method: request.method,
      headers: request.headers,
      credentials: "include",
    });
    const token = readCsrfToken();
    if (token) retry.headers.set("X-CSRF-Token", token);
    return fetch(retry);
  },
};

// Cookie auth: same-origin via the Vite proxy in dev. fetch is resolved per call (not
// captured at creation) so test mocks can patch it.
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "include",
  fetch: (request) => fetch(request),
});
api.use(csrf, retryAfterRefresh);

interface Problem {
  code?: string;
  detail?: string;
  title?: string;
}

/** Human-readable message from an RFC 7807 body (or a fallback). */
export function problemMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error && typeof error === "object") {
    const p = error as Problem;
    return p.detail ?? p.title ?? fallback;
  }
  return fallback;
}
