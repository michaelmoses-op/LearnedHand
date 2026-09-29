import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { api, problemMessage } from "../api/client";
import { askDocument, type AskCitation, type AskSource } from "./ask";

type Section = {
  id: string;
  parent_id: string | null;
  ordinal: number;
  depth: number;
  title: string;
  body: string | null;
  readable: boolean;
};

export function Reader({ documentId }: { documentId: string }) {
  const qId = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [sources, setSources] = useState<AskSource[]>([]);
  const [citations, setCitations] = useState<AskCitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [tutor, setTutor] = useState(false);
  const [focusSection, setFocusSection] = useState<string | null>(null);

  const doc = useQuery({
    queryKey: ["document", documentId],
    queryFn: async () => {
      const { data, error: err } = await api.GET("/api/v1/documents/{document_id}", {
        params: { path: { document_id: documentId } },
      });
      if (err || !data) throw new Error(problemMessage(err, "Document not found"));
      return data;
    },
  });

  const sections = useQuery({
    queryKey: ["sections", documentId],
    queryFn: async () => {
      const { data, error: err } = await api.GET("/api/v1/documents/{document_id}/sections", {
        params: { path: { document_id: documentId } },
      });
      if (err || !data) throw new Error(problemMessage(err, "Failed to load sections"));
      return data.items as Section[];
    },
  });

  async function onAsk(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setAnswer("");
    setSources([]);
    setCitations([]);
    setError(null);
    setStatus("starting");
    await askDocument(
      documentId,
      q,
      {
        onStatus: (stage) => setStatus(stage),
        onSources: (items) => setSources(items),
        onToken: (text) => setAnswer((prev) => prev + text),
        onCitations: (items) => setCitations(items),
        onDone: () => {
          setStatus(null);
          setAsking(false);
        },
        onError: (_code, detail) => {
          setError(detail);
          setStatus(null);
          setAsking(false);
        },
      },
      tutor ? "tutor" : "answer",
    );
  }

  if (doc.isPending) return <p role="status">Loading…</p>;
  if (doc.isError) return <p role="alert">{doc.error.message}</p>;

  return (
    <article>
      <p className="mb-4">
        <Link to="/" className="underline">
          ← Library
        </Link>
      </p>
      <h2 className="text-xl font-semibold">{doc.data.title}</h2>
      <p className="text-sm text-neutral-600">
        {doc.data.format.toUpperCase()} · {doc.data.status}
        {doc.data.status === "ready" && (
          <>
            {" · "}
            <Link
              to="/documents/$documentId/concepts"
              params={{ documentId }}
              className="underline"
            >
              Concepts
            </Link>
            {" · "}
            <Link to="/documents/$documentId/notes" params={{ documentId }} className="underline">
              Notes
            </Link>
            {" · "}
            <Link to="/documents/$documentId/study" params={{ documentId }} className="underline">
              Study
            </Link>
          </>
        )}
      </p>

      <form className="my-6 space-y-2" onSubmit={onAsk}>
        <label htmlFor={qId} className="block font-medium">
          Ask a question
        </label>
        <textarea
          id={qId}
          className="w-full border border-neutral-300 p-2"
          rows={3}
          value={question}
          disabled={asking || doc.data.status !== "ready"}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={tutor} onChange={(e) => setTutor(e.target.checked)} />
          Tutor mode (guide me instead of answering directly)
        </label>
        <button
          type="submit"
          className="underline disabled:opacity-50"
          disabled={asking || !question.trim() || doc.data.status !== "ready"}
        >
          {asking ? "Thinking…" : "Ask"}
        </button>
        {doc.data.status !== "ready" && (
          <p role="status" className="text-sm text-neutral-600">
            Ingest must finish before you can ask questions.
          </p>
        )}
        {status && (
          <p role="status" className="text-sm text-neutral-600">
            {status}…
          </p>
        )}
        {error && (
          <p role="alert" className="text-red-700">
            {error}
          </p>
        )}
      </form>

      {answer && (
        <section aria-labelledby="answer-heading" className="mb-8">
          <h3 id="answer-heading" className="font-semibold">
            Answer
          </h3>
          <div className="mt-2 whitespace-pre-wrap">{answer}</div>
          {citations.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-3 text-sm">
              {citations.map((c) => (
                <li key={c.chunk_id}>
                  <button
                    type="button"
                    className="underline"
                    onClick={() => {
                      setFocusSection(c.section_id);
                      document
                        .getElementById(`section-${c.section_id}`)
                        ?.scrollIntoView({ behavior: "smooth", block: "start" });
                    }}
                  >
                    [{c.index}]
                  </button>
                </li>
              ))}
            </ul>
          )}
          {sources.length > 0 && citations.length === 0 && (
            <p className="mt-2 text-sm text-neutral-600">{sources.length} sources retrieved.</p>
          )}
        </section>
      )}

      <section aria-labelledby="sections-heading">
        <h3 id="sections-heading" className="font-semibold">
          Contents
        </h3>
        {sections.isPending && <p role="status">Loading sections…</p>}
        {sections.isError && <p role="alert">{sections.error.message}</p>}
        <ol className="mt-4 space-y-6">
          {(sections.data ?? []).map((s) => (
            <li
              key={s.id}
              id={`section-${s.id}`}
              className={focusSection === s.id ? "ring-2 ring-neutral-800" : undefined}
              style={{ paddingLeft: `${s.depth * 0.75}rem` }}
            >
              <h4 className="font-medium">{s.title}</h4>
              {s.readable && s.body ? (
                <p className="mt-1 whitespace-pre-wrap text-neutral-800">{s.body}</p>
              ) : (
                <p className="mt-1 text-sm text-neutral-500">Past your reading progress.</p>
              )}
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}
