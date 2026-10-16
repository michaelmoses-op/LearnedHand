import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { Notes } from "./Notes";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const DOC = "11111111-1111-1111-1111-111111111111";

function renderIt(node: React.ReactNode) {
  const root = createRootRoute({
    component: () => <QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>,
  });
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => null });
  const doc = createRoute({
    getParentRoute: () => root,
    path: "/documents/$documentId",
    component: () => null,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, doc]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  render(<RouterProvider router={router} />);
}

test("notes: search sends the query and lists results; add sends a highlight", async () => {
  const seen: string[] = [];
  let posted: unknown = null;
  const note = {
    id: "n1",
    kind: "note",
    anchor_ordinal: 3,
    quote: null,
    body: "keeper is lonely",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
  server.use(
    http.get(`*/api/v1/documents/${DOC}/notes`, ({ request }) => {
      seen.push(new URL(request.url).searchParams.get("q") ?? "");
      return HttpResponse.json({ items: [note] });
    }),
    http.post(`*/api/v1/documents/${DOC}/notes`, async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({ ...note, id: "n2", kind: "highlight" }, { status: 201 });
    }),
  );
  renderIt(<Notes documentId={DOC} />);
  expect(await screen.findByText("keeper is lonely")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Search notes"), "lonely");
  await screen.findByText("keeper is lonely");
  expect(seen).toContain("lonely");

  await userEvent.type(screen.getByLabelText(/Highlighted passage/), "orchard blossom");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("keeper is lonely");
  expect(posted).toEqual({ kind: "highlight", body: "", quote: "orchard blossom" });
});
