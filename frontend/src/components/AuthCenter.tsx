import type { ReactNode } from "react";

/** Centered parchment card on the welcome background (verify, reset, confirmations). */
export function AuthCenter({ children }: { children: ReactNode }) {
  return (
    <div className="welcome-page flex min-h-screen items-center justify-center px-4 py-10">
      <div className="auth-card w-full max-w-md">{children}</div>
    </div>
  );
}
