import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { api, problemMessage } from "../api/client";
import { askDocument, type AskCitation, type AskSource } from "./ask";
import { ConceptMap } from "./ConceptMap";
import { Notes } from "./Notes";
import { useProgress, useSaveProgress } from "./progress";
import { ReadingPosition } from "./ReadingPosition";
import { SectionText, type ChunkSpan } from "./SectionText";
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
  chunks: ChunkSpan[];
};

const TABS = [
  { id: "read", label: "Read & Ask", needsReady: false },
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
  const [tab, setTab] = useState<TabId>("read");
  const tabsId = useId();
  const progress = useProgress(documentId);
  const saveProgress = useSaveProgress(documentId);

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
    document
      .getElementById(`section-${sectionId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
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
  // The furthest section the reader has finished: where their bookmark sits.
  const gateNow = progress.data?.max_ordinal ?? -1;
  const hereId =
    (sections.data ?? []).find((s) => s.chunks.some((c) => c.ordinal === gateNow))?.id ??
    (sections.data ?? [])
      .filter((s) => s.last_chunk_ordinal !== null && s.last_chunk_ordinal <= gateNow)
      .sort(
        (x, y) =>
          (y.last_chunk_ordinal ?? 0) - (x.last_chunk_ordinal ?? 0) || y.ordinal - x.ordinal,
      )[0]?.id;

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
        {tab === "read" && (
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
                        title="Jump to this passage below"
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
            <hr className="rule my-8" />

            <section aria-labelledby="sections-heading">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <h3 id="sections-heading" className="text-2xl font-semibold">
                  Contents
                </h3>
                <p className="muted text-sm">
                  Tip: click a paragraph (or double-click it) to mark how far you have read, or use{" "}
                  <em>Finished here</em> for a whole section.
                </p>
              </div>
              {sections.isPending && <p role="status">Loading sections…</p>}
              {sections.isError && (
                <p role="alert" className="alert">
                  {sections.error.message}
                </p>
              )}
              {saveProgress.isError && (
                <p role="alert" className="alert mt-3">
                  {saveProgress.error.message}
                </p>
              )}
              <ol className="mt-4 space-y-4">
                {(sections.data ?? []).map((s) => {
                  const last = s.last_chunk_ordinal;
                  const gate = progress.data?.max_ordinal ?? -1;
                  const finished = last !== null && last <= gate;
                  const here = s.id === hereId;
                  const atEnd = here && finished;
                  const mark = () => {
                    if (last !== null && !saveProgress.isPending) saveProgress.mutate(last);
                  };
                  return (
                    <li
                      key={s.id}
                      id={`section-${s.id}`}
                      className={`rounded-sm border p-4 ${
                        here
                          ? "border-gold bg-gold/10 shadow-[inset_4px_0_0_var(--color-burgundy)]"
                          : "border-transparent"
                      } ${focusSection === s.id ? "ring-2 ring-gold" : ""}`}
                      style={{ marginLeft: `${s.depth * 0.75}rem` }}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h4 className="text-lg font-semibold">{s.title}</h4>
                        {last !== null && (
                          <div className="flex items-center gap-2">
                            {here && (
                              <span className="rounded-sm bg-burgundy px-2 py-0.5 text-xs font-bold tracking-wide text-vellum uppercase">
                                You are here
                              </span>
                            )}
                            {finished && !here && (
                              <span className="muted text-sm" title="You have read this section">
                                Read ✓
                              </span>
                            )}
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              aria-label={`${atEnd ? "Bookmarked" : "Finished here"}, ${s.title}`}
                              disabled={saveProgress.isPending || atEnd}
                              onClick={mark}
                            >
                              {atEnd ? "Bookmarked" : "Finished here"}
                            </button>
                          </div>
                        )}
                      </div>
                      {s.readable && s.body ? (
                        <SectionText
                          title={s.title}
                          body={s.body}
                          chunks={s.chunks}
                          progress={gate}
                          showBookmark={here}
                          disabled={saveProgress.isPending}
                          onMark={(ordinal) => saveProgress.mutate(ordinal)}
                        />
                      ) : (
                        <div
                          title={last !== null ? "Double-click to mark as finished" : undefined}
                          onDoubleClick={() => {
                            window.getSelection()?.removeAllRanges();
                            mark();
                          }}
                        >
                          <p className="muted mt-2 text-sm italic">Past your reading progress.</p>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>
          </>
        )}

        {tab === "concepts" && <ConceptMap documentId={documentId} />}
        {tab === "notes" && <Notes documentId={documentId} />}
        {tab === "study" && <Study documentId={documentId} />}
      </div>
    </article>
  );
}
