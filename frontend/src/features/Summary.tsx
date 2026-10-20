import { useSummaries } from "./summaries";

/** The book's overall summary, then a summary per section. */
export function Summary({ documentId, onAsk }: { documentId: string; onAsk?: () => void }) {
  const q = useSummaries(documentId);
  return (
    <article>
      <h3 className="theme-article-title">Summary</h3>
      <p className="theme-muted mb-4 text-sm">
        An overview of the whole book, then each section.{" "}
        {onAsk && (
          <>
            Want to dig deeper?{" "}
            <button type="button" className="theme-link" onClick={onAsk}>
              Ask a question
            </button>
            .
          </>
        )}
      </p>
      {q.isPending && <p role="status">Loading…</p>}
      {q.isError && (
        <p role="alert" className="alert">
          {q.error.message}
        </p>
      )}
      {q.data && !q.data.book && q.data.sections.length === 0 && (
        <p role="status" className="notice">
          No summaries yet. They appear once the book has finished processing.
        </p>
      )}
      {q.data?.book && (
        <section aria-labelledby="book-summary-heading" className="welcome-demo mb-6">
          <h4 id="book-summary-heading" className="font-lockup text-sm tracking-[0.14em] text-[#7A1F1F]">
            The whole book
          </h4>
          <p className="prose-book mt-2 whitespace-pre-wrap">{q.data.book}</p>
        </section>
      )}
      <ol className="space-y-5">
        {q.data?.sections.map((s) => (
          <li key={s.section_id} style={{ marginLeft: `${s.depth * 0.75}rem` }}>
            <h4 className="text-lg font-semibold">{s.title}</h4>
            <p className="prose-book mt-1 whitespace-pre-wrap">{s.body}</p>
          </li>
        ))}
      </ol>
    </article>
  );
}
