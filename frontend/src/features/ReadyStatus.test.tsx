import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, test } from "vitest";
import { ReadyStatus } from "./ReadyStatus";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderIt() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReadyStatus />
    </QueryClientProvider>,
  );
}

test("shows ready status", async () => {
  server.use(http.get("*/readyz", () => HttpResponse.json({ status: "ready" })));
  renderIt();
  expect(await screen.findByText(/API status: ready/)).toBeInTheDocument();
});

test("shows alert when API is down", async () => {
  server.use(http.get("*/readyz", () => HttpResponse.json({ status: "x" }, { status: 503 })));
  renderIt();
  expect(await screen.findByRole("alert")).toHaveTextContent("API not ready");
});
