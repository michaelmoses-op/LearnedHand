import type { ReactNode } from "react";
import { BackToTop } from "./BackToTop";
import { Logo } from "./Logo";

export function AppShell({
  email,
  onLogout,
  children,
}: {
  email: string;
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <div className="welcome-page flex min-h-screen flex-col">
      <header className="welcome-bar flex h-16 shrink-0 items-center justify-between gap-4 px-6 sm:px-12">
        <Logo size="nav" tone="dark" to="/library" />
        <div className="flex min-w-0 items-center gap-3 sm:gap-5">
          <p className="font-lockup m-0 hidden max-w-[16rem] truncate text-sm tracking-[0.12em] text-[#E2C27A] sm:block">
            {email}
          </p>
          <button type="button" className="welcome-nav-signin cursor-pointer" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8 sm:px-10">{children}</main>
      <BackToTop />
    </div>
  );
}
