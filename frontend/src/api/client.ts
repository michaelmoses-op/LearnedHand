import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Cookie auth (Phase 1): same-origin via the Vite proxy in dev, so credentials are included.
// fetch is resolved per call (not captured at creation) so test mocks can patch it.
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: "include",
  fetch: (request) => fetch(request),
});
