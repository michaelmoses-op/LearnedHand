/** Tan quill on walnut (favicon); dark ink on light backgrounds. */
export const QUILL_INK_ON_WALNUT = "#E2C27A";
export const QUILL_INK_ON_LIGHT = "#3A2418";

/** Quill pen mark from the Learned Hand brand reference (viewBox 0 0 64 64). */
export function QuillMark({
  size = 32,
  cut = "var(--color-vellum)",
  ink,
  className,
}: {
  size?: number;
  /** Stroke color for feather cut lines; should match the background behind the mark. */
  cut?: string;
  /** Fill/stroke color for the mark. Set explicitly so link styles cannot tint the quill burgundy. */
  ink?: string;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-hidden
      className={className}
      style={{
        flex: "none",
        ["--quill-cut" as string]: cut,
        ...(ink ? { color: ink } : {}),
      }}
    >
      <path d="M22 42C22 28 36 10 54 6C54 22 42 40 22 42Z" fill="currentColor" />
      <path
        d="M30 33L23 28M37 26L31 18M44 18L40 10M30 33L38 38M37 26L46 31M44 18L51 25"
        stroke="var(--quill-cut)"
        strokeWidth="1.2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M10 54L54 6"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M10 54C14 60 18 50 22 58S30 60 34 56S42 58 46 57S54 58 60 56"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
