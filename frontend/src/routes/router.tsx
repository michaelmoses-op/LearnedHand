import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { ReadyStatus } from "../features/ReadyStatus";

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: function Index() {
    return (
      <main className="mx-auto max-w-2xl p-8">
        <h1 className="text-2xl font-semibold">LearnedHand</h1>
        <ReadyStatus />
      </main>
    );
  },
});

export const router = createRouter({ routeTree: rootRoute.addChildren([indexRoute]) });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
