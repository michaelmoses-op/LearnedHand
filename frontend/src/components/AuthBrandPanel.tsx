import { Link } from "@tanstack/react-router";
import { QUILL_INK_ON_WALNUT, QuillMark } from "./QuillMark";

/** Walnut sidebar on auth pages (login mock). */
export function AuthBrandPanel() {
  return (
    <aside className="auth-brand flex flex-col justify-center gap-5 px-10 py-12 lg:w-[540px] lg:shrink-0 lg:px-16 lg:py-16">
      <Link
        to="/"
        aria-label="Learned Hand home"
        className="logo-brand inline-block w-fit"
        style={{ color: QUILL_INK_ON_WALNUT }}
      >
        <QuillMark size={104} cut="#3A2418" ink={QUILL_INK_ON_WALNUT} />
      </Link>
      <p className="font-lockup text-[26px] tracking-[0.14em] text-[#E2C27A]">Learned Hand</p>
      <p className="max-w-[380px] text-[1.65rem] leading-snug text-[#F5F0E3] italic lg:text-[30px] lg:leading-[1.3]">
        Every good reading begins with a question.
      </p>
    </aside>
  );
}
