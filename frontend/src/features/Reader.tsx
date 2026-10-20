import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { api, problemMessage } from "../api/client";
import { askDocument, type AskCitation, type AskSource } from "./ask";
import { ConceptMap } from "./ConceptMap";
import { Notes } from "./Notes";
import { BookText } from "./BookText";
import { ingestErrorMessage } from "./ingestError";
import { Summary } from "./Summary";

type Section = {
  id: string;
  parent_id: string | null;
  ordinal: number;
  depth: number;
  title: string;
  body: string | null;
};

const TABS = [
  { id: "read", label: "Read & Ask", needsReady: false },
  { id: "summary", label: "Summary", needsReady: true },
  { id: "concepts", label: "Concepts", needsReady: true },
  { id: "notes", label: "Notes", needsReady: true },
] as const;
type TabId = (typeof TABS)[number]["id"];

function sectionTitle(sections: Section[] | undefined, sectionId: string): string {
  return sections?.find((s) => s.id === sectionId)?.title ?? "Passage";
}

function sourceRows(
  citations: AskCitation[],
  sources: AskSource[],
  sections: Section[] | undefined,
): { key: string; label: string; sectionId: string; count: number }[] {
  const bySection = new Map<string, number>();
  for (const c of citations) {
    bySection.set(c.section_id, (bySection.get(c.section_id) ?? 0) + 1);
  }
  if (bySection.size > 0) {
    return [...bySection.entries()].map(([sectionId, count]) => ({
      key: sectionId,
      sectionId,
      label: sectionTitle(sections, sectionId),
      count,
    }));
  }
  for (const s of sources) {
    bySection.set(s.section_id, (bySection.get(s.section_id) ?? 0) + 1);
  }
  return [...bySection.entries()].map(([sectionId, count]) => ({
    key: sectionId,
    sectionId,
    label: sectionTitle(sections, sectionId),
    count,
  }));
}

export function Reader({ documentId }: { documentId: string }) {
  const qId = useId();
  const scrollRef = useRef<HTMLElement>(null);
  const [question, setQuestion] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
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
    const el = document.getElementById(`section-${sectionId}`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
    scrollRef.current?.focus({ preventScroll: true });
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
    setLastQuestion(q);
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
          setQuestion("");
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

  if (doc.isPending) {
    return (
      <div className="reader-page flex min-h-screen items-center justify-center">
        <p role="status">Loading…</p>
      </div>
    );
  }
  if (doc.isError) {
    return (
      <div className="reader-page flex min-h-screen items-center justify-center p-6">
        <p role="alert" className="alert">
          {doc.error.message}
        </p>
      </div>
    );
  }

  const ready = doc.data.status === "ready";
  const sectionList = sections.data ?? [];
  const asideRows = sourceRows(citations, sources, sectionList);

  return (
    <article className="reader-page flex h-screen max-h-screen flex-col overflow-hidden">
      <header className="reader-bar">
        <Link to="/library" className="reader-bar-brand">
          Learned Hand
        </Link>
        <div role="tablist" aria-label="Book sections" className="reader-tabs">
          {TABS.map((t) => {
            const disabled = t.needsReady && !ready;
            return (
              <button
                key={t.id}
                id={`${tabsId}-tab-${t.id}`}
                type="button"
                role="tab"
                className="reader-tab"
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
        <h1 className="reader-bar-title" title={doc.data.title}>
          {doc.data.title}
        </h1>
      </header>

      {doc.data.status === "failed" && (
        <p role="alert" className="alert mx-5 mt-4 shrink-0">
          {ingestErrorMessage(doc.data.error)}
        </p>
      )}

      <div
        id={`${tabsId}-panel`}
        role="tabpanel"
        aria-labelledby={`${tabsId}-tab-${tab}`}
        className="reader-body min-h-0 flex-1"
      >
        {tab === "read" && (
          <div className="reader-grid min-h-0 flex-1">
            <nav
              aria-labelledby="reader-index-heading"
              className="reader-scroll hidden min-h-0 overflow-auto lg:block"
            >
              <h2 id="reader-index-heading" className="reader-index-heading">
                Index
              </h2>
              {sections.isPending && <p role="status">Loading…</p>}
              {sections.isError && (
                <p role="alert" className="alert">
                  {sections.error.message}
                </p>
              )}
              {sectionList.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="reader-index-row"
                  aria-current={focusSection === s.id ? "true" : undefined}
                  style={{ paddingLeft: `${s.depth * 0.65}rem` }}
                  onClick={() => openContents(s.id)}
                >
                  <span>{s.title}</span>
                  <span className="reader-index-dots" aria-hidden />
                </button>
              ))}
            </nav>

            <main ref={scrollRef} tabIndex={-1} className="reader-center min-h-0">
              <div className="reader-panel reader-scroll">
                {(answer || asking || lastQuestion) && (
                  <section aria-labelledby="answer-heading">
                    <p className="reader-panel-eyebrow">Your question</p>
                    {lastQuestion && (
                      <h3 id="answer-heading" className="reader-panel-question">
                        {lastQuestion}
                      </h3>
                    )}
                    {status && (
                      <p role="status" className="muted mb-3 text-sm">
                        {status}…
                      </p>
                    )}
                    {error && (
                      <p role="alert" className="alert mb-3">
                        {error}
                      </p>
                    )}
                    {answer && (
                      <div className="prose-book mb-6 whitespace-pre-wrap leading-relaxed">{answer}</div>
                    )}
                    {citations.length > 0 && (
                      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm lg:hidden">
                        <span className="muted">Sources:</span>
                        {citations.map((c) => (
                          <button
                            key={c.chunk_id}
                            type="button"
                            className="reader-cite-btn"
                            title="Jump to this passage"
                            onClick={() => openContents(c.section_id)}
                          >
                            [{c.index}] {sectionTitle(sectionList, c.section_id)}
                          </button>
                        ))}
                      </div>
                    )}
                    {(answer || lastQuestion) && sectionList.length > 0 && (
                      <hr className="rule mb-6 border-[#1f1a14]/20" />
                    )}
                  </section>
                )}

                {!lastQuestion && !asking && ready && (
                  <p className="muted mb-6 italic">Propose a question below, or read the text.</p>
                )}
                {!ready && (
                  <p role="status" className="notice mb-6 text-sm">
                    Ingest must finish before you can ask questions.
                  </p>
                )}

                <section aria-labelledby="sections-heading" className="reader-text-flow w-full">
                  <h3 id="sections-heading" className="reader-index-heading">
                    Text
                  </h3>
                  <ol className="m-0 w-full list-none space-y-0 p-0">
                    {sectionList.map((s) => (
                      <li
                        key={s.id}
                        id={`section-${s.id}`}
                        data-focused={focusSection === s.id ? "true" : undefined}
                        className="reader-section-block w-full"
                        style={{ paddingLeft: `${s.depth * 0.75}rem` }}
                      >
                        <h4 className="text-lg font-semibold">{s.title}</h4>
                        {s.body ? (
                          <BookText title={s.title} body={s.body} layout="reader" />
                        ) : (
                          <p className="muted mt-2 text-sm italic">No text in this section.</p>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              </div>

              <form className="reader-ask-row shrink-0" onSubmit={onAsk}>
                <label htmlFor={qId} className="sr-only">
                  Ask a question about this book
                </label>
                <input
                  id={qId}
                  type="text"
                  className="reader-ask-input"
                  placeholder="Propose a question to the text"
                  value={question}
                  disabled={asking || !ready}
                  onChange={(e) => setQuestion(e.target.value)}
                />
                <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4 cursor-pointer accent-burgundy"
                    checked={tutor}
                    onChange={(e) => setTutor(e.target.checked)}
                  />
                  Tutor
                </label>
                <button
                  type="submit"
                  className="reader-ask-submit shrink-0"
                  disabled={asking || !question.trim() || !ready}
                >
                  {asking ? "Thinking…" : "Ask"}
                </button>
              </form>
            </main>

            <aside
              aria-labelledby="reader-sources-heading"
              className="reader-scroll hidden min-h-0 overflow-auto lg:block"
            >
              <h2 id="reader-sources-heading" className="reader-aside-heading">
                Sources
              </h2>
              {asideRows.length === 0 && (
                <p className="muted text-sm italic">Citations from answers appear here.</p>
              )}
              {asideRows.map((row) => (
                <div key={row.key} className="reader-aside-row">
                  <button
                    type="button"
                    className="reader-cite-btn shrink-0"
                    onClick={() => openContents(row.sectionId)}
                  >
                    {row.label}
                  </button>
                  <span className="reader-index-dots" aria-hidden />
                  <span className="shrink-0 tabular-nums">{row.count}</span>
                </div>
              ))}
            </aside>
          </div>
        )}

        {tab === "summary" && (
          <div className="reader-tabpanel reader-scroll">
            <div className="reader-tabpanel-inner">
              <Summary documentId={documentId} onAsk={() => setTab("read")} />
            </div>
          </div>
        )}
        {tab === "concepts" && (
          <div className="reader-tabpanel reader-scroll">
            <div className="reader-tabpanel-inner reader-tabpanel-inner--wide">
              <ConceptMap documentId={documentId} />
            </div>
          </div>
        )}
        {tab === "notes" && (
          <div className="reader-tabpanel reader-scroll">
            <div className="reader-tabpanel-inner">
              <Notes documentId={documentId} />
            </div>
          </div>
        )}
      </div>
    </article>
  );
}
