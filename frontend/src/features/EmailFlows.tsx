import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { AuthCenter } from "../components/AuthCenter";
import { api, problemMessage } from "../api/client";

export function VerifyEmail({ token }: { token: string }) {
  const verify = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/v1/auth/verify-email", { body: { token } });
      if (error) throw new Error(problemMessage(error, "Verification failed"));
    },
  });
  const started = useRef(false);
  useEffect(() => {
    if (!started.current && token) {
      started.current = true; // single-use token: never fire twice (StrictMode)
      verify.mutate();
    }
  });
  if (verify.isError) {
    return (
      <AuthCenter>
        <p role="alert" className="alert">
          {verify.error.message}
        </p>
      </AuthCenter>
    );
  }
  if (verify.isSuccess) {
    return (
      <AuthCenter>
        <p role="status" className="notice border-0 bg-transparent p-0 text-base">
          Email verified.{" "}
          <Link to="/login" className="theme-link">
            Continue
          </Link>
        </p>
      </AuthCenter>
    );
  }
  return (
    <AuthCenter>
      <p role="status" className="muted text-base">
        Verifying…
      </p>
    </AuthCenter>
  );
}

export function ResetPassword({ token }: { token: string | undefined }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const request = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/v1/auth/password-reset/request", { body: { email } });
      if (error) throw new Error(problemMessage(error));
    },
  });
  const confirm = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/v1/auth/password-reset/confirm", {
        body: { token: token ?? "", new_password: password },
      });
      if (error) throw new Error(problemMessage(error, "Reset failed"));
    },
  });

  if (token) {
    if (confirm.isSuccess) {
      return (
        <AuthCenter>
          <p role="status" className="notice border-0 bg-transparent p-0 text-base">
            Password updated.{" "}
            <Link to="/login" className="theme-link">
              Log in
            </Link>
          </p>
        </AuthCenter>
      );
    }
    return (
      <AuthCenter>
        <p className="font-lockup text-[13px] tracking-[0.14em] text-[#7A1F1F]">Account</p>
        <h1 className="auth-card-title mt-1.5 mb-5 border-b-[3px] border-double border-[#1F1A14] pb-3 text-[28px] leading-tight font-normal italic">
          Choose a new password
        </h1>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            confirm.mutate();
          }}
        >
          <div>
            <label htmlFor="new-password" className="auth-label">
              New password (12+ characters)
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
              className="auth-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {confirm.isError && (
            <p role="alert" className="alert">
              {confirm.error.message}
            </p>
          )}
          <button type="submit" className="btn-lockup btn-lockup-primary w-full">
            Set password
          </button>
        </form>
      </AuthCenter>
    );
  }
  if (request.isSuccess) {
    return (
      <AuthCenter>
        <p role="status" className="notice border-0 bg-transparent p-0 text-base leading-relaxed">
          If that address has an account, a reset link is on its way.
        </p>
      </AuthCenter>
    );
  }
  return (
    <AuthCenter>
      <p className="font-lockup text-[13px] tracking-[0.14em] text-[#7A1F1F]">Account</p>
      <h1 className="auth-card-title mt-1.5 mb-5 border-b-[3px] border-double border-[#1F1A14] pb-3 text-[28px] leading-tight font-normal italic">
        Reset password
      </h1>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          request.mutate();
        }}
      >
        <div>
          <label htmlFor="reset-email" className="auth-label">
            Email
          </label>
          <input
            id="reset-email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            className="auth-field"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {request.isError && (
          <p role="alert" className="alert">
            {request.error.message}
          </p>
        )}
        <button type="submit" className="btn-lockup btn-lockup-primary w-full">
          Send reset link
        </button>
        <p className="text-center text-base">
          <Link to="/login" className="theme-link">
            Back to sign in
          </Link>
        </p>
      </form>
    </AuthCenter>
  );
}
