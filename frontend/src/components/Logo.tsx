import { Link } from "@tanstack/react-router";
import { QUILL_INK_ON_LIGHT, QUILL_INK_ON_WALNUT, QuillMark } from "./QuillMark";

type LogoProps = {
  /** Horizontal lockup for the site header; compact for auth panels; nav for the welcome bar. */
  size?: "header" | "compact" | "nav";
  tone?: "light" | "dark";
  /** When set, the lockup links home (default for the main header). */
  to?: "/" | "/library" | null;
  className?: string;
};

const SIZES = {
  header: { mark: 52, text: "text-[1.35rem] sm:text-[1.4rem]" },
  compact: { mark: 40, text: "text-[1.15rem]" },
  nav: { mark: 40, text: "text-sm" },
} as const;

/** Wordmark + quill: brand lockup (name is “Learned Hand”, two words). */
export function Logo({ size = "header", tone = "light", to = "/", className = "" }: LogoProps) {
  const { mark, text } = SIZES[size];
  const dark = tone === "dark";
  const ink = dark ? "#E2C27A" : "#1F1A14";
  const body = (
    <span className={`inline-flex items-center gap-3 no-underline ${className}`}>
      <QuillMark
        size={mark}
        cut={dark ? "#3A2418" : "var(--color-parchment)"}
        ink={dark ? QUILL_INK_ON_WALNUT : QUILL_INK_ON_LIGHT}
      />
      <span className={`font-lockup ${text} tracking-[0.14em] text-inherit`}>Learned Hand</span>
    </span>
  );

  if (to) {
    return (
      <Link
        to={to}
        aria-label="Learned Hand home"
        className="logo-brand inline-block hover:opacity-90"
        style={{ color: ink }}
      >
        {body}
      </Link>
    );
  }
  return body;
}
