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
    },
    {
      id: S2,
      parent_id: null,
      ordinal: 1,
      depth: 0,
      title: "Orchard",
      body: "Blossom and bees.",
    },
  ],
};

function renderIt() {
  server.use(
    http.get(`*/api/v1/documents/${DOC}`, () => HttpResponse.json(doc)),
    http.get(`*/api/v1/documents/${DOC}/sections`, () => HttpResponse.json(sections)),
    http.get(`*/api/v1/documents/${DOC}/concepts`, () =>
      HttpResponse.json({ sections: [], concepts: [] }),
    ),
    http.get(`*/api/v1/documents/${DOC}/summaries`, () =>
      HttpResponse.json({
        book: "A book about harbors and orchards.",
        sections: [{ section_id: S1, title: "Harbor", ordinal: 0, depth: 0, body: "Nets." }],
      }),
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

test("Summary, Concepts and Notes open beneath the tab bar without leaving the page", async () => {
  renderIt();
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Read & Ask", "Summary", "Concepts", "Notes"]);
  expect(screen.getByRole("tab", { name: "Read & Ask" })).toHaveAttribute("aria-selected", "true");
  // Ask box and the whole book's text share one page, chat first.
  expect(screen.getByLabelText(/Ask a question/)).toBeInTheDocument();
  expect(screen.getByText("Nets and tide.")).toBeInTheDocument();
  expect(screen.getByText("Blossom and bees.")).toBeInTheDocument();
  expect(screen.queryByText(/reading progress/i)).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Summary" }));
  expect(await screen.findByText("A book about harbors and orchards.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Four Places" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
  expect(await screen.findByText(/No notes yet/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Concepts" }));
  expect(await screen.findByText(/No concepts yet/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Read & Ask" }));
  expect(await screen.findByText("Nets and tide.")).toBeInTheDocument();
});

test("arrow keys move between tabs", async () => {
  renderIt();
  const first = await screen.findByRole("tab", { name: "Read & Ask" });
  first.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
});
