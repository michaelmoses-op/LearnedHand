import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { Summary } from "./Summary";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const DOC = "11111111-1111-1111-1111-111111111111";

function renderIt() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Summary documentId={DOC} />
    </QueryClientProvider>,
  );
}

test("shows the book summary and one per section", async () => {
  server.use(
    http.get(`*/api/v1/documents/${DOC}/summaries`, () =>
      HttpResponse.json({
        book: "A book about four places.",
        sections: [
          { section_id: "s1", title: "Harbor", ordinal: 0, depth: 0, body: "Nets and tide." },
          { section_id: "s2", title: "Orchard", ordinal: 1, depth: 0, body: "Blossom and bees." },
        ],
      }),
    ),
  );
  renderIt();
  expect(await screen.findByText("A book about four places.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Harbor" })).toBeInTheDocument();
  expect(screen.getByText("Blossom and bees.")).toBeInTheDocument();
});

test("explains when there are no summaries yet", async () => {
  server.use(
    http.get(`*/api/v1/documents/${DOC}/summaries`, () =>
      HttpResponse.json({ book: null, sections: [] }),
    ),
  );
  renderIt();
  expect(await screen.findByText(/No summaries yet/)).toBeInTheDocument();
});
