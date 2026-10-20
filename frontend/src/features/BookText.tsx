/** Paragraphs (blank-line separated) of a section body. */
export function paragraphsOf(title: string, body: string): string[] {
  const paras = body
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  // The section heading is shown separately; don't repeat it as the first paragraph.
  if (paras[0] && paras[0].toLowerCase() === title.trim().toLowerCase()) paras.shift();
  return paras;
}

/** EPUB line breaks are often hard `\n`; reflow for the responsive reader column. */
export function reflowParagraphForReader(text: string): string {
  return text
    .replace(/\s*\n\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Section text laid out like a printed page: one `<p>` per paragraph. */
export function BookText({
  title,
  body,
  layout = "default",
}: {
  title: string;
  body: string;
  /** Reader panel: full width, left-aligned measure. */
  layout?: "default" | "reader";
}) {
  const paras = paragraphsOf(title, body);
  const textClass = layout === "reader" ? "book-text reader-book-text mt-3" : "book-text mt-3";
  return (
    <div className={textClass}>
      {paras.map((p, i) => {
        const text = layout === "reader" ? reflowParagraphForReader(p) : p;
        return (
          <div key={i}>
            <p className={i === 0 ? "dropcap" : undefined}>{text}</p>
          </div>
        );
      })}
    </div>
  );
}
