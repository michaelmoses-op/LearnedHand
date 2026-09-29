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
import { ConceptMap } from "./ConceptMap";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const DOC = "11111111-1111-1111-1111-111111111111";
const S1 = "aaaaaaaa-0000-0000-0000-000000000001";
const S2 = "aaaaaaaa-0000-0000-0000-000000000002";
const C1 = "cccccccc-0000-0000-0000-000000000001";

const map = {
  progress: 5,
  sections: [
    { id: S1, title: "Harbor", ordinal: 0, chunks: 2, fully_read: true },
    { id: S2, title: "Orchard", ordinal: 1, chunks: 3, fully_read: false },
  ],
  concepts: [
    {
      id: C1,
      name: "lighthouse",
      sections: 2,
      chunks: 3,
      cells: [
        { section_id: S1, chunks: 2, intensity: 1 },
        { section_id: S2, chunks: 1, intensity: 0.33 },
      ],
    },
  ],
};

function renderIt() {
  const root = createRootRoute({
    component: () => (
      <QueryClientProvider client={new QueryClient()}>
        <ConceptMap documentId={DOC} />
      </QueryClientProvider>
    ),
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

test("renders the heat map and shows a trajectory with spoiler-safe notes on select", async () => {
  server.use(
    http.get(`*/api/v1/documents/${DOC}/concepts`, () => HttpResponse.json(map)),
    http.get(`*/api/v1/documents/${DOC}/concepts/${C1}/trajectory`, () =>
      HttpResponse.json({
        concept_id: C1,
        name: "lighthouse",
        points: [
          {
            section_id: S1,
            section_title: "Harbor",
            section_ordinal: 0,
            first_ordinal: 0,
            chunks: 2,
            note: "The keeper lights the lamp.",
          },
          {
            section_id: S2,
            section_title: "Orchard",
            section_ordinal: 1,
            first_ordinal: 2,
            chunks: 1,
            note: null,
          },
        ],
      }),
    ),
  );
  renderIt();
  const row = await screen.findByRole("button", { name: /lighthouse, in 2 sections/ });
  expect(row).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(row);
  expect(await screen.findByText("The keeper lights the lamp.")).toBeInTheDocument();
  expect(screen.getByText("Finish this section to see a note.")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Trajectory of lighthouse/ })).toBeInTheDocument();
});

test("shows an empty state when nothing has been reached", async () => {
  server.use(
    http.get(`*/api/v1/documents/${DOC}/concepts`, () =>
      HttpResponse.json({ progress: null, sections: [], concepts: [] }),
    ),
  );
  renderIt();
  expect(await screen.findByText(/No concepts yet/)).toBeInTheDocument();
});
