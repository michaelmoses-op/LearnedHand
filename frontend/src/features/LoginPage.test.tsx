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
import { LoginPage } from "./LoginPage";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderIt() {
  const root = createRootRoute({
    component: () => (
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <LoginPage />
      </QueryClientProvider>
    ),
  });
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => null });
  const login = createRoute({ getParentRoute: () => root, path: "/login", component: () => null });
  const signup = createRoute({ getParentRoute: () => root, path: "/signup", component: () => null });
  const reset = createRoute({
    getParentRoute: () => root,
    path: "/reset-password",
    component: () => null,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, login, signup, reset]),
    history: createMemoryHistory({ initialEntries: ["/login"] }),
  });
  render(<RouterProvider router={router} />);
}

test("login page matches the split layout and copy", async () => {
  server.use(http.post("*/api/v1/auth/login", () => HttpResponse.json(null, { status: 401 })));
  renderIt();
  expect(await screen.findByText("Learned Hand")).toBeInTheDocument();
  expect(screen.getByText(/Every good reading begins with a question/i)).toBeInTheDocument();
  expect(screen.getByText("Sign in to your library")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "Welcome back" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Enter" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Forgot password?" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/signup");
  expect(screen.queryByRole("button", { name: /Google/i })).not.toBeInTheDocument();
});
