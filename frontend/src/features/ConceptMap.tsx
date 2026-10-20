import { useMemo, useState } from "react";
import type { ConceptMap as ConceptMapData, ConceptRow } from "./concepts";
import { useConceptMap, useTrajectory } from "./concepts";

function sectionLabel(title: string, index: number): string {
  const short = title.length > 18 ? `${title.slice(0, 17)}…` : title;
  return `${index + 1}. ${short}`;
}

function ConceptLegend() {
  return (
    <div className="concept-legend" aria-hidden>
      <span className="concept-legend-label">Mentions in section</span>
      <span className="concept-legend-scale">
        <span className="concept-legend-swatch concept-legend-swatch--none" />
        <span>none</span>
        <span className="concept-legend-swatch concept-legend-swatch--low" />
        <span className="concept-legend-swatch concept-legend-swatch--high" />
        <span>more</span>
      </span>
      <span className="concept-legend-hint">Columns follow section order in the book.</span>
    </div>
  );
}

function MatrixRow({
  row,
  data,
  selected,
  onSelect,
}: {
  row: ConceptRow;
  data: ConceptMapData;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const cells = useMemo(() => new Map(row.cells.map((c) => [c.section_id, c])), [row.cells]);
  const active = row.id === selected;
  const label = `${row.name}, in ${row.sections} sections`;

  return (
    <tr
      className={`concept-matrix-row ${active ? "concept-matrix-row--active" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={label}
      aria-pressed={active}
      onClick={() => onSelect(row.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(row.id);
        }
      }}
    >
      <th scope="row" className="concept-matrix-name">
        <span className="concept-matrix-name-text">{row.name}</span>
        <span className="concept-matrix-name-meta">
          {row.sections} section{row.sections === 1 ? "" : "s"} · {row.chunks} passage
          {row.chunks === 1 ? "" : "s"}
        </span>
      </th>
      {data.sections.map((s) => {
        const cell = cells.get(s.id);
        const title = cell
          ? `${row.name} · ${s.title}: ${cell.chunks} passage${cell.chunks === 1 ? "" : "s"}`
          : `${row.name} · ${s.title}: not mentioned`;
        return (
          <td key={s.id} className="concept-matrix-cell">
            <span
              className={`concept-matrix-swatch ${cell ? "concept-matrix-swatch--on" : ""}`}
              style={cell ? { opacity: 0.22 + 0.78 * cell.intensity } : undefined}
              title={title}
            />
          </td>
        );
      })}
    </tr>
  );
}

function ConceptMatrix({
  data,
  selected,
  onSelect,
}: {
  data: ConceptMapData;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="concept-matrix-wrap reader-scroll">
      <table className="concept-matrix">
        <caption className="sr-only">
          How often each concept appears in each section of the book
        </caption>
        <thead>
          <tr>
            <th scope="col" className="concept-matrix-corner">
              Concept
            </th>
            {data.sections.map((s, i) => (
              <th key={s.id} scope="col" className="concept-matrix-section">
                <abbr title={s.title} className="concept-matrix-section-abbr">
                  {i + 1}
                </abbr>
                <span className="concept-matrix-section-title">{sectionLabel(s.title, i)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.concepts.map((row) => (
            <MatrixRow
              key={row.id}
              row={row}
              data={data}
              selected={selected}
              onSelect={onSelect}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Selected concept: presence across sections and optional notes. */
function TrajectoryPanel({ documentId, conceptId }: { documentId: string; conceptId: string }) {
  const q = useTrajectory(documentId, conceptId);
  const map = useConceptMap(documentId);
  if (q.isPending) return <p role="status">Loading…</p>;
  if (q.isError) {
    return (
      <p role="alert" className="alert">
        {q.error.message}
      </p>
    );
  }

  const sections = map.data?.sections ?? [];
  const counts = new Map(q.data.points.map((p) => [p.section_id, p.chunks]));
  const max = Math.max(1, ...counts.values());

  return (
    <section aria-labelledby="traj-heading" className="concept-detail welcome-demo">
      <p className="font-lockup text-xs tracking-[0.14em] text-[#7A1F1F]">Selected concept</p>
      <h3 id="traj-heading" className="concept-detail-title">
        {q.data.name}
      </h3>
      <p className="theme-muted mb-4 text-sm">Passages per section, in reading order.</p>

      <div className="concept-bars" role="img" aria-label={`Trajectory of ${q.data.name}`}>
        {sections.map((s) => {
          const n = counts.get(s.id) ?? 0;
          const pct = (n / max) * 100;
          return (
            <div key={s.id} className="concept-bar-row" title={`${s.title}: ${n} passage${n === 1 ? "" : "s"}`}>
              <span className="concept-bar-label">{s.title}</span>
              <span className="concept-bar-track">
                <span className="concept-bar-fill" style={{ width: `${pct}%` }} />
              </span>
              <span className="concept-bar-count tabular-nums">{n}</span>
            </div>
          );
        })}
      </div>

      {q.data.points.length > 0 && (
        <ol className="concept-detail-notes mt-5 space-y-3">
          {q.data.points.map((p) => (
            <li key={p.section_id} className="concept-detail-note">
              <p className="font-medium">{p.section_title}</p>
              <p className="theme-muted text-sm">
                {p.chunks} passage{p.chunks === 1 ? "" : "s"}
              </p>
              {p.note && <p className="mt-1 text-[15px] leading-snug">{p.note}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function ConceptMap({ documentId }: { documentId: string }) {
  const map = useConceptMap(documentId);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <article className="concept-map">
      <h3 className="theme-article-title">Concepts</h3>
      <p className="theme-muted mb-4 max-w-3xl text-sm leading-relaxed">
        Recurring ideas extracted from your book. Each cell shows how much that concept appears in
        that section—darker means more passages. Choose a row to see its path through the work.
      </p>
      {map.isPending && <p role="status">Loading…</p>}
      {map.isError && (
        <p role="alert" className="alert">
          {map.error.message}
        </p>
      )}
      {map.data && map.data.concepts.length === 0 && (
        <p role="status" className="notice">
          No concepts yet. Make sure the book has finished processing.
        </p>
      )}
      {map.data && map.data.concepts.length > 0 && (
        <>
          <ConceptLegend />
          <div className={`concept-map-body ${selected ? "concept-map-body--split" : ""}`}>
            <ConceptMatrix
              data={map.data}
              selected={selected}
              onSelect={(id) => setSelected((cur) => (cur === id ? null : id))}
            />
            {selected && (
              <TrajectoryPanel documentId={documentId} conceptId={selected} />
            )}
          </div>
        </>
      )}
    </article>
  );
}
