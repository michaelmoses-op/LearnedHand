import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthBrandPanel } from "../components/AuthBrandPanel";
import { AuthCenter } from "../components/AuthCenter";
import { AuthForm } from "./AuthForm";
import { useLogin, useSignup } from "./auth";

export function SignupPage() {
  const signup = useSignup();
  const login = useLogin();
  const navigate = useNavigate();
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <AuthCenter>
        <p role="status" className="notice border-0 bg-transparent p-0 text-base leading-relaxed">
          Check your email to verify your address, then{" "}
          <Link to="/login" className="theme-link">
            log in
          </Link>
          .
        </p>
      </AuthCenter>
    );
  }

  return (
    <div className="welcome-page auth-split flex min-h-screen flex-col lg:flex-row">
      <AuthBrandPanel />
      <div className="flex flex-1 items-center justify-center px-6 py-10 lg:px-8">
        <div className="auth-card w-full max-w-[420px]">
          <p className="font-lockup text-[13px] tracking-[0.14em] text-[#7A1F1F]">
            Create your library
          </p>
          <h1 className="auth-card-title mt-1.5 mb-1 border-b-[3px] border-double border-[#1F1A14] pb-3 text-[32px] leading-tight font-normal italic">
            Begin reading
          </h1>
          <AuthForm
            variant="lockup"
            submitLabel="Sign up"
            autoComplete="new-password"
            pending={signup.isPending}
            serverError={signup.error?.message}
            onSubmit={async (v) => {
              const accepted = await signup.mutateAsync(v).catch(() => undefined);
              if (!accepted) return;
              if (!accepted.email_verification_required) {
                await login.mutateAsync(v).then(
                  () => navigate({ to: "/library" }),
                  () => undefined,
                );
                return;
              }
              setDone(true);
            }}
            footer={
              <p className="mt-5 text-center text-base">
                Already have an account?{" "}
                <Link to="/login" className="theme-link font-normal">
                  Sign in
                </Link>
              </p>
            }
          />
        </div>
      </div>
    </div>
  );
}
