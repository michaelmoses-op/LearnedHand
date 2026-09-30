import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Navigate,
  Outlet,
  useNavigate,
} from "@tanstack/react-router";
import { useState } from "react";
import { AuthForm } from "../features/AuthForm";
import { useLogin, useLogout, useMe, useSignup } from "../features/auth";
import { ResetPassword, VerifyEmail } from "../features/EmailFlows";
import { Library } from "../features/Library";
import { Reader } from "../features/Reader";
import { ReadyStatus } from "../features/ReadyStatus";

const rootRoute = createRootRoute({
  component: () => (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 pb-10 sm:px-8">
      <header className="pt-8 pb-6 text-center">
        <p className="eyebrow">A reading companion for the humanities</p>
        <h1 className="mt-1 text-4xl font-bold tracking-wide sm:text-5xl">
          <Link to="/" className="text-ink no-underline hover:text-burgundy">
            LearnedHand
          </Link>
        </h1>
        <hr className="rule mx-auto mt-4 max-w-md" />
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  ),
});

function Home() {
  const me = useMe();
  const logout = useLogout();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (!me.data) return <Navigate to="/login" />;
  return (
    <>
      <div className="mb-6 flex items-center justify-between gap-4">
        <p className="muted">
          Signed in as <span className="font-semibold text-ink">{me.data.email}</span>
        </p>
        <button className="btn btn-secondary btn-sm" onClick={() => logout.mutate()}>
          Log out
        </button>
      </div>
      <Library />
      <div className="muted mt-10 text-center text-sm">
        <ReadyStatus />
      </div>
    </>
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
  const login = useLogin();
  const navigate = useNavigate();
  return (
    <div className="panel mx-auto max-w-md p-8">
      <h2 className="mb-5 text-2xl font-semibold">Log in</h2>
      <AuthForm
        submitLabel="Log in"
        autoComplete="current-password"
        pending={login.isPending}
        serverError={login.error?.message}
        onSubmit={async (v) => {
          await login.mutateAsync(v).then(
            () => navigate({ to: "/" }),
            () => undefined,
          );
        }}
      />
      <p className="mt-5">
        <Link to="/reset-password" search={{ token: undefined }} className="link-action">
          Forgot password?
        </Link>
      </p>
      <p className="mt-2">
        No account?{" "}
        <Link to="/signup" className="link-action">
          Sign up
        </Link>
      </p>
    </div>
  );
}

function Signup() {
  const signup = useSignup();
  const [done, setDone] = useState(false);
  if (done)
    return (
      <p role="status" className="notice mx-auto max-w-md">
        Check your email to verify your address, then{" "}
        <Link to="/login" className="link-action">
          log in
        </Link>
        .
      </p>
    );
  return (
    <div className="panel mx-auto max-w-md p-8">
      <h2 className="mb-5 text-2xl font-semibold">Create an account</h2>
      <AuthForm
        submitLabel="Sign up"
        autoComplete="new-password"
        pending={signup.isPending}
        serverError={signup.error?.message}
        onSubmit={async (v) => {
          await signup.mutateAsync(v).then(
            () => setDone(true),
            () => undefined,
          );
        }}
      />
    </div>
  );
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
    return token ? <VerifyEmail token={token} /> : <p role="alert">Missing token.</p>;
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

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: Home });
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
