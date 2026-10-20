import { Link } from "@tanstack/react-router";
import { useNavigate } from "@tanstack/react-router";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthForm } from "./AuthForm";
import { useLogin } from "./auth";

export function LoginPage() {
  const login = useLogin();
  const navigate = useNavigate();

  return (
    <div className="welcome-page auth-split flex min-h-screen flex-col lg:flex-row">
      <AuthBrandPanel />
      <div className="flex flex-1 items-center justify-center px-6 py-10 lg:px-8">
        <div className="auth-card w-full max-w-[420px]">
          <p className="font-lockup text-[13px] tracking-[0.14em] text-[#7A1F1F]">
            Sign in to your library
          </p>
          <h1 className="auth-card-title mt-1.5 mb-1 border-b-[3px] border-double border-[#1F1A14] pb-3 text-[32px] leading-tight font-normal italic">
            Welcome back
          </h1>
          <AuthForm
            variant="lockup"
            submitLabel="Enter"
            autoComplete="current-password"
            pending={login.isPending}
            serverError={login.error?.message}
            onSubmit={async (v) => {
              await login.mutateAsync(v).then(
                () => navigate({ to: "/library" }),
                () => undefined,
              );
            }}
            afterPassword={
              <div className="mt-3.5 mb-5 flex justify-end text-base">
                <Link
                  to="/reset-password"
                  search={{ token: undefined }}
                  className="theme-link"
                >
                  Forgot password?
                </Link>
              </div>
            }
            footer={
              <p className="mt-5 text-center text-base">
                New here?{" "}
                <Link to="/signup" className="theme-link font-normal">
                  Create an account
                </Link>
              </p>
            }
          />
        </div>
      </div>
    </div>
  );
}
