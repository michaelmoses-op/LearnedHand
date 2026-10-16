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

/** Section text laid out like a printed page: one `<p>` per paragraph. */
export function BookText({ title, body }: { title: string; body: string }) {
  const paras = paragraphsOf(title, body);
  return (
    <div className="book-text mt-3">
      {paras.map((p, i) => (
        <div key={i}>
          <p className={i === 0 ? "dropcap" : undefined}>{p}</p>
        </div>
      ))}
    </div>
  );
}
