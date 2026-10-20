import { useId, useState, type FormEvent } from "react";
import { useAddNote, useDeleteNote, useNotes } from "./notes";

export function Notes({ documentId }: { documentId: string }) {
  const searchId = useId();
  const bodyId = useId();
  const quoteId = useId();
  const [search, setSearch] = useState("");
  const [body, setBody] = useState("");
  const [quote, setQuote] = useState("");
  const notes = useNotes(documentId, search.trim());
  const add = useAddNote(documentId);
  const del = useDeleteNote(documentId);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = quote.trim();
    if (!q && !body.trim()) return;
    await add
      .mutateAsync(
        q
          ? { kind: "highlight", quote: q, body: body.trim() }
          : { kind: "note", body: body.trim() },
      )
      .then(
        () => {
          setBody("");
          setQuote("");
        },
        () => undefined,
      );
  }

  return (
    <article>
      <h3 className="theme-article-title">Notes and highlights</h3>
      <p className="theme-muted mb-4 text-sm">
        Keep your own notes and highlighted passages for this book, and search them later.
      </p>

      <form className="mb-8 space-y-3" onSubmit={onSubmit}>
        <label htmlFor={quoteId} className="auth-label">
          Highlighted passage (optional)
        </label>
        <textarea
          id={quoteId}
          className="auth-field"
          rows={2}
          value={quote}
          onChange={(e) => setQuote(e.target.value)}
        />
        <label htmlFor={bodyId} className="auth-label">
          Note
        </label>
        <textarea
          id={bodyId}
          className="auth-field"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <button
          type="submit"
          className="btn-lockup btn-lockup-primary"
          disabled={add.isPending || (!quote.trim() && !body.trim())}
        >
          Save
        </button>
        {add.isError && (
          <p role="alert" className="alert">
            {add.error.message}
          </p>
        )}
      </form>

      <label htmlFor={searchId} className="auth-label">
        Search notes
      </label>
      <input
        id={searchId}
        type="search"
        className="auth-field mb-4"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {notes.isPending && <p role="status">Loading…</p>}
      {notes.isError && (
        <p role="alert" className="alert">
          {notes.error.message}
        </p>
      )}
      {notes.data && notes.data.length === 0 && (
        <p role="status" className="notice">
          No notes yet.
        </p>
      )}
      <ul className="space-y-3">
        {notes.data?.map((n) => (
          <li
            key={n.id}
            className="welcome-demo border-l-4 border-l-[#E2C27A] p-4"
          >
            <p className="font-lockup text-xs tracking-[0.14em] text-[#7A1F1F]">
              {n.kind === "highlight" ? "Highlight" : "Note"}
            </p>
            {n.quote && (
              <blockquote className="my-2 border-l-2 border-rule pl-3 italic">{n.quote}</blockquote>
            )}
            {n.body && <p className="whitespace-pre-wrap">{n.body}</p>}
            <button
              type="button"
              className="btn-lockup btn-lockup-sm mt-3 border border-[#7A1F1F] bg-transparent text-[#7A1F1F]"
              onClick={() => del.mutate(n.id)}
              aria-label={`Delete ${n.kind}`}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </article>
  );
}
