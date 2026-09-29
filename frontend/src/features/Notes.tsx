import { Link } from "@tanstack/react-router";
import { useId, useState, type FormEvent } from "react";
import { useAddNote, useDeleteNote, useNotes } from "./study";

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
      <p className="mb-4">
        <Link to="/documents/$documentId" params={{ documentId }} className="underline">
          ← Back to book
        </Link>
      </p>
      <h2 className="text-xl font-semibold">Notes and highlights</h2>
      <p className="mb-4 text-sm text-neutral-600">
        Notes attach to your current reading position and only show up once you have read that far.
      </p>

      <form className="mb-6 space-y-2" onSubmit={onSubmit}>
        <label htmlFor={quoteId} className="block font-medium">
          Highlighted passage (optional)
        </label>
        <textarea
          id={quoteId}
          className="w-full border border-neutral-300 p-2"
          rows={2}
          value={quote}
          onChange={(e) => setQuote(e.target.value)}
        />
        <label htmlFor={bodyId} className="block font-medium">
          Note
        </label>
        <textarea
          id={bodyId}
          className="w-full border border-neutral-300 p-2"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <button
          type="submit"
          className="underline disabled:opacity-50"
          disabled={add.isPending || (!quote.trim() && !body.trim())}
        >
          Save
        </button>
        {add.isError && (
          <p role="alert" className="text-red-700">
            {add.error.message}
          </p>
        )}
      </form>

      <label htmlFor={searchId} className="block font-medium">
        Search notes
      </label>
      <input
        id={searchId}
        type="search"
        className="mb-4 w-full border border-neutral-300 p-2"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {notes.isPending && <p role="status">Loading…</p>}
      {notes.isError && <p role="alert">{notes.error.message}</p>}
      {notes.data && notes.data.length === 0 && <p role="status">No notes yet.</p>}
      <ul className="space-y-3">
        {notes.data?.map((n) => (
          <li key={n.id} className="border border-neutral-200 p-3">
            <p className="text-xs text-neutral-500">
              {n.kind === "highlight" ? "Highlight" : "Note"} · passage {n.anchor_ordinal}
            </p>
            {n.quote && <blockquote className="border-l-2 pl-2 italic">{n.quote}</blockquote>}
            {n.body && <p className="whitespace-pre-wrap">{n.body}</p>}
            <button
              type="button"
              className="mt-1 text-sm underline"
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
