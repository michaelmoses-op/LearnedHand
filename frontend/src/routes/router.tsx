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
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-2xl font-semibold">LearnedHand</h1>
      <Outlet />
    </main>
  ),
});

function Home() {
  const me = useMe();
  const logout = useLogout();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (!me.data) return <Navigate to="/login" />;
  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <p>{me.data.email}</p>
        <button className="underline" onClick={() => logout.mutate()}>
          Log out
        </button>
      </div>
      <Library />
      <div className="mt-8 text-sm text-neutral-600">
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
    <>
      <h2 className="mb-4 text-xl">Log in</h2>
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
      <p className="mt-4">
        <Link to="/reset-password" search={{ token: undefined }} className="underline">
          Forgot password?
        </Link>
      </p>
      <p className="mt-2">
        No account?{" "}
        <Link to="/signup" className="underline">
          Sign up
        </Link>
      </p>
    </>
  );
}

function Signup() {
  const signup = useSignup();
  const [done, setDone] = useState(false);
  if (done)
    return (
      <p role="status">
        Check your email to verify your address, then{" "}
        <Link to="/login" className="underline">
          log in
        </Link>
        .
      </p>
    );
  return (
    <>
      <h2 className="mb-4 text-xl">Create an account</h2>
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
    </>
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
