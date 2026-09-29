import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { File as NodeFile } from "node:buffer";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { Library } from "./Library";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const doc = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Godel Escher Bach",
  original_filename: "geb.epub",
  format: "epub",
  file_size: 2_097_152,
  status: "uploaded",
  created_at: "2026-01-01T00:00:00Z",
};

function renderIt() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Library />
    </QueryClientProvider>,
  );
}

test("shows empty state", async () => {
  server.use(
    http.get("*/api/v1/documents", () => HttpResponse.json({ items: [], next_cursor: null })),
  );
  renderIt();
  expect(await screen.findByText(/library is empty/i)).toBeInTheDocument();
});

test("lists documents", async () => {
  server.use(
    http.get("*/api/v1/documents", () => HttpResponse.json({ items: [doc], next_cursor: null })),
  );
  renderIt();
  expect(await screen.findByText("Godel Escher Bach", { selector: "p" })).toBeInTheDocument();
  expect(screen.getByText(/EPUB · 2.0 MB · uploaded/)).toBeInTheDocument();
});

test("upload sends raw file with encoded filename and shows server errors", async () => {
  let seenName: string | null = null;
  server.use(
    http.get("*/api/v1/documents", () => HttpResponse.json({ items: [], next_cursor: null })),
    http.post("*/api/v1/documents", ({ request }) => {
      seenName = request.headers.get("x-filename");
      return HttpResponse.json(
        { code: "unsupported_file", detail: "Only .epub and .pdf files are accepted" },
        { status: 415 },
      );
    }),
  );
  renderIt();
  // jsdom's File is not a valid fetch body under Node; use the native one.
  const file = new NodeFile(["PK\u0003\u0004data"], "Café.epub") as unknown as File;
  await userEvent.upload(await screen.findByLabelText(/Upload a book/), file);
  expect(await screen.findByRole("alert")).toHaveTextContent("Only .epub and .pdf");
  expect(seenName).toBe("Caf%C3%A9.epub");
});
