import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { Welcome } from "./Welcome";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderIt() {
  server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(null, { status: 401 })));
  const root = createRootRoute({
    component: () => (
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Welcome />
      </QueryClientProvider>
    ),
  });
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => null });
  const signup = createRoute({
    getParentRoute: () => root,
    path: "/signup",
    component: () => null,
  });
  const login = createRoute({ getParentRoute: () => root, path: "/login", component: () => null });
  const router = createRouter({
    routeTree: root.addChildren([index, signup, login]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  render(<RouterProvider router={router} />);
}

test("welcome page shows brand, hero, and sign-up paths", async () => {
  renderIt();
  expect(await screen.findByText("Learned Hand")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { level: 1, name: /Put your questions to the book/i }),
  ).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Create an account/i }).length).toBeGreaterThanOrEqual(
    2,
  );
  const signIn = screen.getAllByRole("link", { name: "Sign in" });
  expect(signIn.some((el) => el.getAttribute("href") === "/login")).toBe(true);
  expect(screen.getByText(/not a shortcut around reading/i)).toBeInTheDocument();
});
