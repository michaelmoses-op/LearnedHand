import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
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
  if (verify.isError) return <p role="alert">{verify.error.message}</p>;
  if (verify.isSuccess)
    return (
      <p role="status">
        Email verified.{" "}
        <Link to="/" className="underline">
          Continue
        </Link>
      </p>
    );
  return <p role="status">Verifying…</p>;
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
  const input = "mt-1 block w-full rounded border border-neutral-400 px-3 py-2";

  if (token) {
    if (confirm.isSuccess)
      return (
        <p role="status">
          Password updated.{" "}
          <Link to="/login" className="underline">
            Log in
          </Link>
        </p>
      );
    return (
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          confirm.mutate();
        }}
      >
        <label htmlFor="new-password">New password (12+ characters)</label>
        <input
          id="new-password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={128}
          required
          className={input}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {confirm.isError && <p role="alert">{confirm.error.message}</p>}
        <button type="submit" className="rounded bg-blue-700 px-4 py-2 text-white">
          Set password
        </button>
      </form>
    );
  }
  if (request.isSuccess)
    return <p role="status">If that address has an account, a reset link is on its way.</p>;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        request.mutate();
      }}
    >
      <label htmlFor="reset-email">Email</label>
      <input
        id="reset-email"
        type="email"
        autoComplete="email"
        required
        maxLength={254}
        className={input}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      {request.isError && <p role="alert">{request.error.message}</p>}
      <button type="submit" className="rounded bg-blue-700 px-4 py-2 text-white">
        Send reset link
      </button>
    </form>
  );
}
