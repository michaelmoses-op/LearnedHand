import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { api, problemMessage } from "../api/client";
import { askDocument, type AskCitation, type AskSource } from "./ask";
import { ConceptMap } from "./ConceptMap";
import { Notes } from "./Notes";
import { ReadingPosition } from "./ReadingPosition";
import { Study } from "./Study";

type Section = {
  id: string;
  parent_id: string | null;
  ordinal: number;
  depth: number;
  title: string;
  body: string | null;
  readable: boolean;
  last_chunk_ordinal: number | null;
};

const TABS = [
  { id: "ask", label: "Ask", needsReady: false },
  { id: "contents", label: "Contents", needsReady: false },
  { id: "concepts", label: "Concepts", needsReady: true },
  { id: "notes", label: "Notes", needsReady: true },
  { id: "study", label: "Study", needsReady: true },
] as const;
type TabId = (typeof TABS)[number]["id"];

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
  const [tab, setTab] = useState<TabId>("ask");
  const tabsId = useId();

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

  function openContents(sectionId: string) {
    setFocusSection(sectionId);
    setTab("contents");
    // Wait for the Contents tab to render before scrolling to the cited section.
    setTimeout(
      () =>
        document
          .getElementById(`section-${sectionId}`)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      50,
    );
  }

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, ready: boolean) {
    const enabled = TABS.filter((t) => ready || !t.needsReady);
    const i = enabled.findIndex((t) => t.id === tab);
    const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const next = enabled[(i + dir + enabled.length) % enabled.length];
    if (dir !== 0 && next) {
      e.preventDefault();
      setTab(next.id);
      document.getElementById(`${tabsId}-tab-${next.id}`)?.focus();
    }
  }

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
  if (doc.isError)
    return (
      <p role="alert" className="alert">
        {doc.error.message}
      </p>
    );

  const ready = doc.data.status === "ready";

  return (
    <article>
      <p className="mb-4">
        <Link to="/" className="link-action">
          ← Library
        </Link>
      </p>

      <header className="panel mb-6 p-6">
        <p className="eyebrow">
          {doc.data.format.toUpperCase()} · {doc.data.status}
        </p>
        <h2 className="mt-1 text-3xl font-semibold">{doc.data.title}</h2>
        {ready && sections.data && (
          <div className="mt-4">
            <ReadingPosition documentId={documentId} sections={sections.data} />
          </div>
        )}
      </header>

      <div role="tablist" aria-label="Book sections" className="tabs">
        {TABS.map((t) => {
          const disabled = t.needsReady && !ready;
          return (
            <button
              key={t.id}
              id={`${tabsId}-tab-${t.id}`}
              type="button"
              role="tab"
              className="tab"
              aria-selected={tab === t.id}
              aria-controls={`${tabsId}-panel`}
              aria-disabled={disabled}
              tabIndex={tab === t.id ? 0 : -1}
              title={disabled ? "Available once the book has finished processing" : undefined}
              onClick={() => !disabled && setTab(t.id)}
              onKeyDown={(e) => onTabKey(e, ready)}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        id={`${tabsId}-panel`}
        role="tabpanel"
        aria-labelledby={`${tabsId}-tab-${tab}`}
        className="tabpanel"
      >
        {tab === "ask" && (
          <>
            <form className="space-y-3" onSubmit={onAsk}>
              <label htmlFor={qId} className="label">
                Ask a question about what you have read
              </label>
              <textarea
                id={qId}
                className="field"
                rows={3}
                value={question}
                disabled={asking || !ready}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 cursor-pointer accent-burgundy"
                  checked={tutor}
                  onChange={(e) => setTutor(e.target.checked)}
                />
                Tutor mode (guide me with hints instead of answering directly)
              </label>
              <button type="submit" className="btn" disabled={asking || !question.trim() || !ready}>
                {asking ? "Thinking…" : "Ask"}
              </button>
              {!ready && (
                <p role="status" className="notice text-sm">
                  Ingest must finish before you can ask questions.
                </p>
              )}
              {status && (
                <p role="status" className="muted text-sm">
                  {status}…
                </p>
              )}
              {error && (
                <p role="alert" className="alert">
                  {error}
                </p>
              )}
            </form>

            {answer && (
              <section aria-labelledby="answer-heading" className="mt-8">
                <hr className="rule mb-6" />
                <h3 id="answer-heading" className="text-xl font-semibold">
                  Answer
                </h3>
                <div className="prose-book dropcap mt-2 whitespace-pre-wrap">{answer}</div>
                {citations.length > 0 && (
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                    <span className="muted">Sources:</span>
                    {citations.map((c) => (
                      <button
                        key={c.chunk_id}
                        type="button"
                        className="btn btn-secondary btn-sm"
                        title="Jump to this passage in Contents"
                        onClick={() => openContents(c.section_id)}
                      >
                        [{c.index}]
                      </button>
                    ))}
                  </div>
                )}
                {sources.length > 0 && citations.length === 0 && (
                  <p className="muted mt-2 text-sm">{sources.length} sources retrieved.</p>
                )}
              </section>
            )}
          </>
        )}

        {tab === "contents" && (
          <section aria-labelledby="sections-heading">
            <h3 id="sections-heading" className="text-xl font-semibold">
              Contents
            </h3>
            {sections.isPending && <p role="status">Loading sections…</p>}
            {sections.isError && (
              <p role="alert" className="alert">
                {sections.error.message}
              </p>
            )}
            <ol className="mt-4 space-y-6">
              {(sections.data ?? []).map((s) => (
                <li
                  key={s.id}
                  id={`section-${s.id}`}
                  className={`rounded-sm p-3 ${focusSection === s.id ? "bg-gold/15 ring-2 ring-gold" : ""}`}
                  style={{ marginLeft: `${s.depth * 0.75}rem` }}
                >
                  <h4 className="text-lg font-semibold">{s.title}</h4>
                  {s.readable && s.body ? (
                    <p className="prose-book mt-1 whitespace-pre-wrap">{s.body}</p>
                  ) : (
                    <p className="muted mt-1 text-sm italic">Past your reading progress.</p>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}

        {tab === "concepts" && <ConceptMap documentId={documentId} />}
        {tab === "notes" && <Notes documentId={documentId} />}
        {tab === "study" && <Study documentId={documentId} />}
      </div>
    </article>
  );
}
