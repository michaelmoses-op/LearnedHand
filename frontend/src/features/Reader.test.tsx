import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { Reader } from "./Reader";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const DOC = "11111111-1111-1111-1111-111111111111";
const S1 = "aaaaaaaa-0000-0000-0000-000000000001";
const S2 = "aaaaaaaa-0000-0000-0000-000000000002";

const doc = {
  id: DOC,
  title: "Four Places",
  original_filename: "four.epub",
  format: "epub",
  file_size: 1000,
  status: "ready",
  created_at: "2026-01-01T00:00:00Z",
};
const sections = {
  items: [
    {
      id: S1,
      parent_id: null,
      ordinal: 0,
      depth: 0,
      title: "Harbor",
      body: "Nets and tide.\n\nGulls wheel over the pier.",
      readable: true,
      last_chunk_ordinal: 1,
      chunks: [
        { ordinal: 0, char_start: 0, char_end: 14 },
        { ordinal: 1, char_start: 16, char_end: 42 },
      ],
    },
    {
      id: S2,
      parent_id: null,
      ordinal: 1,
      depth: 0,
      title: "Orchard",
      body: null,
      readable: false,
      last_chunk_ordinal: 3,
      chunks: [],
    },
  ],
};

function renderIt(progress: { current: number }, puts: unknown[] = []) {
  server.use(
    http.get(`*/api/v1/documents/${DOC}`, () => HttpResponse.json(doc)),
    http.get(`*/api/v1/documents/${DOC}/sections`, () => HttpResponse.json(sections)),
    http.get(`*/api/v1/documents/${DOC}/status`, () =>
      HttpResponse.json({
        id: DOC,
        status: "ready",
        ingest_stage: "validate",
        error: null,
        max_ordinal: progress.current,
        updated_at: "2026-01-01T00:00:00Z",
      }),
    ),
    http.put(`*/api/v1/documents/${DOC}/progress`, async ({ request }) => {
      const body = (await request.json()) as { max_ordinal: number };
      puts.push(body);
      progress.current = body.max_ordinal;
      return HttpResponse.json({ document_id: DOC, max_ordinal: body.max_ordinal });
    }),
    http.get(`*/api/v1/documents/${DOC}/concepts`, () =>
      HttpResponse.json({ progress: 0, sections: [], concepts: [] }),
    ),
    http.get(`*/api/v1/documents/${DOC}/notes`, () => HttpResponse.json({ items: [] })),
  );
  const root = createRootRoute({
    component: () => (
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Reader documentId={DOC} />
      </QueryClientProvider>
    ),
  });
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => null });
  const router = createRouter({
    routeTree: root.addChildren([index]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  render(<RouterProvider router={router} />);
}

test("Concepts, Notes and Study open beneath the tab bar without leaving the page", async () => {
  renderIt({ current: 3 });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Read & Ask", "Concepts", "Notes", "Study"]);
  expect(screen.getByRole("tab", { name: "Read & Ask" })).toHaveAttribute("aria-selected", "true");
  // Ask box and contents share one page, chat first.
  expect(screen.getByLabelText(/Ask a question/)).toBeInTheDocument();
  expect(screen.getByText("Nets and tide.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
  expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText(/No notes yet/)).toBeInTheDocument();
  // Still the same page: the book header and the tab bar are all still there.
  expect(screen.getByRole("heading", { name: "Four Places" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Concepts" }));
  expect(await screen.findByText(/No concepts yet/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Read & Ask" }));
  expect(await screen.findByText("Nets and tide.")).toBeInTheDocument();
  expect(screen.getByText("Past your reading progress.")).toBeInTheDocument();
});

test("arrow keys move between tabs", async () => {
  renderIt({ current: 3 });
  const first = await screen.findByRole("tab", { name: "Read & Ask" });
  first.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Concepts" })).toHaveAttribute("aria-selected", "true");
});

test("reading position shows where you are and saves a new position", async () => {
  const progress = { current: 3 };
  const puts: unknown[] = [];
  renderIt(progress, puts);
  const select = await screen.findByLabelText("I have read up to");
  await waitFor(() => expect(select).toHaveDisplayValue("End of “Orchard”"));
  await userEvent.selectOptions(select, "The beginning (first passage only)");
  expect(puts).toEqual([{ max_ordinal: 0 }]);
  await waitFor(() => expect(select).toHaveDisplayValue("The beginning (first passage only)"));
  await userEvent.selectOptions(select, "End of “Orchard”");
  expect(puts).toEqual([{ max_ordinal: 0 }, { max_ordinal: 3 }]);
});

test("the section button marks a whole section; the bookmark shows where you are", async () => {
  const progress = { current: 1 };
  const puts: unknown[] = [];
  renderIt(progress, puts);
  await screen.findByText("Nets and tide.");
  await screen.findByText("You are here");
  await userEvent.click(screen.getByRole("button", { name: "Finished here, Orchard" }));
  await waitFor(() => expect(puts).toEqual([{ max_ordinal: 3 }]));
  await waitFor(() => expect(screen.getByRole("button", { name: /Bookmarked/ })).toBeDisabled());
});

test("double-clicking a paragraph saves the last fully-read passage", async () => {
  const progress = { current: 3 };
  const puts: unknown[] = [];
  renderIt(progress, puts);
  // First paragraph is passage 0 exactly.
  await userEvent.dblClick(await screen.findByText("Nets and tide."));
  await waitFor(() => expect(puts).toEqual([{ max_ordinal: 0 }]));
  // Second paragraph ends passage 1.
  await userEvent.dblClick(screen.getByText("Gulls wheel over the pier."));
  await waitFor(() => expect(puts).toEqual([{ max_ordinal: 0 }, { max_ordinal: 1 }]));
});

test("clicking a paragraph offers a button; read paragraphs and the bookmark reflect progress", async () => {
  const progress = { current: 0 };
  const puts: unknown[] = [];
  renderIt(progress, puts);
  const first = await screen.findByText("Nets and tide.");
  const second = screen.getByText("Gulls wheel over the pier.");
  expect(first).toHaveAttribute("data-read", "true");
  expect(second).not.toHaveAttribute("data-read");
  expect(screen.getByText("You have read up to here")).toBeInTheDocument();

  await userEvent.click(second);
  await userEvent.click(screen.getByRole("button", { name: "I have read up to here" }));
  await waitFor(() => expect(puts).toEqual([{ max_ordinal: 1 }]));
  await waitFor(() =>
    expect(screen.getByText("Gulls wheel over the pier.")).toHaveAttribute("data-read", "true"),
  );
});

test("progress inside a section shows as 'Partway through' in the position picker", async () => {
  renderIt({ current: 2 });
  const select = await screen.findByLabelText("I have read up to");
  await waitFor(() => expect(select).toHaveDisplayValue("Partway through “Orchard”"));
});
