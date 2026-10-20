import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Logo } from "../components/Logo";

function LockupButton({
  to,
  variant,
  children,
}: {
  to: string;
  variant: "primary" | "outline" | "gold";
  children: ReactNode;
}) {
  const className =
    variant === "primary"
      ? "btn-lockup btn-lockup-primary"
      : variant === "gold"
        ? "btn-lockup btn-lockup-gold"
        : "btn-lockup btn-lockup-outline";
  return (
    <Link to={to} className={className}>
      {children}
    </Link>
  );
}

/** Public landing page (design reference: Welcome.dc.html). */
export function Welcome() {
  return (
    <div className="welcome-page flex min-h-screen flex-col">
      <header className="welcome-bar flex h-16 shrink-0 items-center justify-between px-6 sm:px-12">
        <Logo size="nav" tone="dark" to="/" />
        <nav aria-label="Site" className="font-lockup tracking-[0.14em] sm:text-[15px]">
          <Link to="/login" className="welcome-nav-signin">
            Sign in
          </Link>
        </nav>
      </header>

      <div className="grid flex-1 items-center gap-10 px-6 py-12 sm:px-12 lg:grid-cols-[1fr_min(470px,100%)] lg:gap-16 lg:py-16">
        <div>
          <p className="font-lockup text-sm tracking-[0.14em] text-[#7A1F1F]">
            A reader&apos;s companion for difficult books
          </p>
          <h1 className="welcome-hero mt-3 mb-5 max-w-xl text-[2.35rem] leading-[1.08] font-normal italic sm:text-[3.25rem] lg:text-[3.875rem]">
            Put your questions to the book, as you would to a professor.
          </h1>
          <p className="mb-7 max-w-[560px] text-[1.15rem] leading-normal text-[#3F3426] sm:text-[21px] sm:leading-[1.5]">
            Upload a book you own. Read at your own pace, and ask about anything that puzzles you.
            Every answer points to the passage it came from.
          </p>
          <div className="flex flex-wrap gap-3">
            <LockupButton to="/signup" variant="primary">
              Create an account
            </LockupButton>
            <LockupButton to="/login" variant="outline">
              Sign in
            </LockupButton>
          </div>
          <p className="mt-4 text-[15px] text-[#5E5140] italic">Your books stay private to you.</p>
        </div>

        <aside className="welcome-demo" aria-label="Example answer format">
          <p className="font-lockup text-[13px] tracking-[0.14em] text-[#7A1F1F]">
            Question the Fourteenth
          </p>
          <p className="welcome-demo-question mt-1.5 mb-3 border-b-[3px] border-double border-[#1F1A14] pb-2.5 text-[22px] leading-snug italic">
            [A question about the book, in the reader&apos;s own words.]
          </p>
          <p className="font-lockup mb-1 text-[13px] tracking-[0.14em]">
            <span className="text-[#7A1F1F]">I.</span> Objections
          </p>
          <p className="mb-2.5 text-base text-[#3F3426]">
            [Competing readings, marked as outside the book.]
          </p>
          <p className="font-lockup mb-1 text-[13px] tracking-[0.14em]">
            <span className="text-[#7A1F1F]">II.</span> On the contrary
          </p>
          <p className="text-base text-[#3F3426]">
            [The book&apos;s own words, cited.]{" "}
            <span className="text-[#7A1F1F]">ch. 8, p. 153</span>
          </p>
        </aside>
      </div>

      <section
        id="how-it-reads"
        className="w-full border-t-[3px] border-double border-[#1F1A14] px-6 pt-8 pb-10 sm:px-12 sm:pt-9"
      >
        <h2 className="font-lockup mb-4 text-sm tracking-[0.14em] text-[#7A1F1F]">
          Before you upload
        </h2>
        <div className="grid gap-6 text-[1.125rem] leading-relaxed text-[#3F3426] sm:text-[17px] sm:leading-[1.55] lg:grid-cols-2 lg:gap-12 lg:leading-normal">
          <p className="m-0">
            This is not a shortcut around reading. You bring an EPUB or PDF you already own; we keep
            its parts and chapters in order so a question can reach anywhere in the volume—not only
            the page you have open.
          </p>
          <p className="m-0">
            Replies point to passages in <em className="text-[#1F1A14]">your</em> copy. Tutor mode
            may answer with another question. Summaries and notes live on your shelf alone.
          </p>
        </div>
      </section>

      <section
        id="privacy"
        className="mb-6 w-full px-6 text-[17px] leading-normal text-[#3F3426] sm:px-12"
      >
        <h2 className="font-lockup mb-2 text-sm tracking-[0.14em] text-[#7A1F1F]">Privacy</h2>
        <p>
          Each account sees only its own uploads. Your files and notes are not shared with other
          readers, and we do not use your book text to train models.
        </p>
      </section>

      <footer className="welcome-bar flex shrink-0 flex-wrap items-center justify-between gap-4 px-6 py-6 sm:h-24 sm:px-12 sm:py-0">
        <p className="text-2xl text-[#F5F0E3] italic sm:text-[26px]">Begin with a book you own.</p>
        <LockupButton to="/signup" variant="gold">
          Create an account
        </LockupButton>
      </footer>
    </div>
  );
}
