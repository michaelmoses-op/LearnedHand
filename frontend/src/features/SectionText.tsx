/** Renders a section's plain text as book paragraphs (blank line = new paragraph). */
export function paragraphsOf(title: string, body: string): string[] {
  const paras = body
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  // The section heading is shown separately; don't repeat it as the first paragraph.
  const first = paras[0];
  if (first !== undefined && first.toLowerCase() === title.trim().toLowerCase()) paras.shift();
  return paras;
}

export function SectionText({ title, body }: { title: string; body: string }) {
  const paras = paragraphsOf(title, body);
  return (
    <div className="book-text mt-3">
      {paras.map((p, i) => (
        <p key={i} className={i === 0 ? "dropcap" : undefined}>
          {p}
        </p>
      ))}
    </div>
  );
}
