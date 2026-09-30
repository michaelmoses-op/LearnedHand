import { useEffect, useState } from "react";

const SHOW_AFTER_PX = 300;

/** Floating button that appears once you scroll down and returns you to the top of the page. */
export function BackToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > SHOW_AFTER_PX);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!visible) return null;
  return (
    <button
      type="button"
      aria-label="Back to top"
      title="Back to top"
      className="btn fixed right-5 bottom-5 z-50 !rounded-full !px-4 !py-3 text-xl shadow-lg"
      onClick={() => {
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
      }}
    >
      <span aria-hidden="true">↑</span>
    </button>
  );
}
