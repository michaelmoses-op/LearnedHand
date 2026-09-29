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
import { Study } from "./Study";

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

const card = {
  id: "c1",
  front: "What does the text say about lighthouse?",
  back: "The keeper tends it.",
  source_ordinal: 1,
  due_at: "2026-01-01T00:00:00Z",
  reps: 0,
  interval_days: 0,
};

test("flashcard: reveal, then rate", async () => {
  let rated: unknown = null;
  server.use(
    http.get(`*/api/v1/documents/${DOC}/flashcards`, () => HttpResponse.json({ items: [card] })),
    http.get(`*/api/v1/documents/${DOC}/quiz`, () => HttpResponse.json({ items: [] })),
    http.post(`*/api/v1/documents/${DOC}/flashcards/c1/review`, async ({ request }) => {
      rated = await request.json();
      return HttpResponse.json({ ...card, reps: 1 });
    }),
  );
  renderIt(<Study documentId={DOC} />);
  expect(await screen.findByText(card.front)).toBeInTheDocument();
  expect(screen.queryByText(card.back)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Show answer" }));
  expect(screen.getByText(card.back)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Good" }));
  await screen.findByText(card.front);
  expect(rated).toEqual({ rating: "good" });
});

test("quiz: shows feedback and explanation after choosing", async () => {
  server.use(
    http.get(`*/api/v1/documents/${DOC}/flashcards`, () => HttpResponse.json({ items: [] })),
    http.get(`*/api/v1/documents/${DOC}/quiz`, () =>
      HttpResponse.json({
        items: [
          {
            id: "q1",
            question: "Which word is central?",
            choices: ["lighthouse", "quasar", "zephyr"],
            source_ordinal: 0,
            times_answered: 0,
          },
        ],
      }),
    ),
    http.post(`*/api/v1/documents/${DOC}/quiz/q1/answer`, () =>
      HttpResponse.json({ correct: true, answer_index: 0, explanation: "It is about lighthouse." }),
    ),
  );
  renderIt(<Study documentId={DOC} />);
  await userEvent.click(await screen.findByRole("button", { name: "lighthouse" }));
  expect(await screen.findByText(/Correct\./)).toBeInTheDocument();
  expect(screen.getByText(/It is about lighthouse\./)).toBeInTheDocument();
});

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
