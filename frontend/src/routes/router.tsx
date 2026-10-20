import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
  useRouterState,
} from "@tanstack/react-router";
import { AppShell } from "../components/AppShell";
import { AuthCenter } from "../components/AuthCenter";
import { useLogout, useMe } from "../features/auth";
import { LoginPage } from "../features/LoginPage";
import { SignupPage } from "../features/SignupPage";
import { ResetPassword, VerifyEmail } from "../features/EmailFlows";
import { Library } from "../features/Library";
import { Reader } from "../features/Reader";
import { ReadyStatus } from "../features/ReadyStatus";
import { Welcome } from "../features/Welcome";

const PUBLIC_PATHS = new Set(["/", "/login", "/signup", "/verify-email", "/reset-password"]);

function RootLayout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isPublic = PUBLIC_PATHS.has(pathname);
  const isReader = pathname.startsWith("/documents/");
  const isLibrary = pathname === "/library";

  if (isPublic || isLibrary || isReader) {
    if (isReader) {
      return (
        <div className="reader-shell min-h-screen">
          <Outlet />
        </div>
      );
    }
    return <Outlet />;
  }

  return (
    <div className="welcome-page flex min-h-screen items-center justify-center p-6">
      <Outlet />
    </div>
  );
}

const rootRoute = createRootRoute({ component: RootLayout });

function WelcomePage() {
  const me = useMe();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (me.data) return <Navigate to="/library" />;
  return <Welcome />;
}

function LibraryPage() {
  const me = useMe();
  const logout = useLogout();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (!me.data) return <Navigate to="/login" />;
  return (
    <AppShell email={me.data.email} onLogout={() => logout.mutate()}>
      <Library />
      <div className="theme-muted mt-10 text-center text-sm">
        <ReadyStatus />
      </div>
    </AppShell>
  );
}

function DocumentPage() {
  const me = useMe();
  const { documentId } = documentRoute.useParams();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (!me.data) return <Navigate to="/login" />;
  return <Reader documentId={documentId} />;
}

function Login() {
  return <LoginPage />;
}

function Signup() {
  return <SignupPage />;
}

const searchToken = (search: Record<string, unknown>) => ({
  token: typeof search.token === "string" ? search.token : undefined,
});
const verifyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/verify-email",
  validateSearch: searchToken,
  component: function Verify() {
    const { token } = verifyRoute.useSearch();
    return token ? (
      <VerifyEmail token={token} />
    ) : (
      <AuthCenter>
        <p role="alert" className="alert">
          Missing token.
        </p>
      </AuthCenter>
    );
  },
});
const resetRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reset-password",
  validateSearch: searchToken,
  component: function Reset() {
    const { token } = resetRoute.useSearch();
    return <ResetPassword token={token} />;
  },
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: WelcomePage,
});
const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/library",
  component: LibraryPage,
});
const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: Login,
});
const signupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signup",
  component: Signup,
});
const documentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/documents/$documentId",
  component: DocumentPage,
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    libraryRoute,
    loginRoute,
    signupRoute,
    verifyRoute,
    resetRoute,
    documentRoute,
  ]),
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
