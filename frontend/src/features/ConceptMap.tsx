import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { ConceptMap as ConceptMapData, ConceptRow } from "./concepts";
import { useConceptMap, useTrajectory } from "./concepts";

const CELL = 28;
const LABEL_W = 150;
const ROW_H = 26;
const HEADER_H = 8;

/** Heat map: one row per concept, one column per section the reader has reached. */
export function Heatmap({
  data,
  selected,
  onSelect,
}: {
  data: ConceptMapData;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const width = LABEL_W + data.sections.length * CELL;
  const height = HEADER_H + data.concepts.length * ROW_H;
  return (
    <svg
      role="group"
      aria-label="Concept heat map"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="max-w-full"
    >
      {data.concepts.map((row, i) => (
        <HeatRow
          key={row.id}
          row={row}
          y={HEADER_H + i * ROW_H}
          data={data}
          active={row.id === selected}
          onSelect={onSelect}
        />
      ))}
    </svg>
  );
}

function HeatRow({
  row,
  y,
  data,
  active,
  onSelect,
}: {
  row: ConceptRow;
  y: number;
  data: ConceptMapData;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const cells = new Map(row.cells.map((c) => [c.section_id, c]));
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={`${row.name}, in ${row.sections} sections`}
      aria-pressed={active}
      className="cursor-pointer outline-none focus-visible:opacity-80"
      onClick={() => onSelect(row.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(row.id);
        }
      }}
    >
      <rect x={0} y={y} width={LABEL_W + data.sections.length * CELL} height={ROW_H} fill="none" />
      <text x={4} y={y + 17} fontSize={13} fontWeight={active ? 700 : 400} fill="currentColor">
        {row.name.length > 20 ? `${row.name.slice(0, 19)}…` : row.name}
      </text>
      {data.sections.map((s, col) => {
        const cell = cells.get(s.id);
        return (
          <rect
            key={s.id}
            x={LABEL_W + col * CELL + 1}
            y={y + 2}
            width={CELL - 2}
            height={ROW_H - 4}
            rx={3}
            fill={cell ? "#4f46e5" : "#e5e5e5"}
            fillOpacity={cell ? 0.2 + 0.8 * cell.intensity : 0.5}
            stroke={active ? "#111" : "none"}
          >
            <title>
              {cell
                ? `${row.name} · ${s.title}: ${cell.chunks} passage${cell.chunks === 1 ? "" : "s"}`
                : `${row.name} · ${s.title}: not mentioned`}
            </title>
          </rect>
        );
      })}
    </g>
  );
}

/** Line chart of a concept's presence across the reached sections, plus per-section notes. */
function TrajectoryPanel({ documentId, conceptId }: { documentId: string; conceptId: string }) {
  const q = useTrajectory(documentId, conceptId);
  const map = useConceptMap(documentId);
  if (q.isPending) return <p role="status">Loading trajectory…</p>;
  if (q.isError) return <p role="alert">{q.error.message}</p>;
  const sections = map.data?.sections ?? [];
  const counts = new Map(q.data.points.map((p) => [p.section_id, p.chunks]));
  const max = Math.max(1, ...counts.values());
  const W = Math.max(sections.length - 1, 1) * 60 + 20;
  const H = 70;
  const pts = sections.map((s, i) => {
    const x = 10 + i * 60;
    const y = H - 10 - ((counts.get(s.id) ?? 0) / max) * (H - 20);
    return { x, y, s, n: counts.get(s.id) ?? 0 };
  });
  return (
    <section aria-labelledby="traj-heading" className="mt-6">
      <h3 id="traj-heading" className="font-semibold">
        “{q.data.name}” across the book
      </h3>
      <svg
        role="img"
        aria-label={`Trajectory of ${q.data.name}`}
        width={W}
        height={H}
        className="mt-2 max-w-full"
      >
        <polyline
          fill="none"
          stroke="#4f46e5"
          strokeWidth={2}
          points={pts.map((p) => `${p.x},${p.y}`).join(" ")}
        />
        {pts.map((p) => (
          <circle key={p.s.id} cx={p.x} cy={p.y} r={4} fill="#4f46e5">
            <title>{`${p.s.title}: ${p.n} passage${p.n === 1 ? "" : "s"}`}</title>
          </circle>
        ))}
      </svg>
      <ol className="mt-3 space-y-2 text-sm">
        {q.data.points.map((p) => (
          <li key={p.section_id}>
            <span className="font-medium">{p.section_title}</span>{" "}
            <span className="text-neutral-500">
              ({p.chunks} passage{p.chunks === 1 ? "" : "s"})
            </span>
            <p className={p.note ? "" : "text-neutral-500 italic"}>
              {p.note ?? "Finish this section to see a note."}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ConceptMap({ documentId }: { documentId: string }) {
  const map = useConceptMap(documentId);
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <article>
      <p className="mb-4">
        <Link to="/documents/$documentId" params={{ documentId }} className="underline">
          ← Back to book
        </Link>
      </p>
      <h2 className="text-xl font-semibold">Concepts</h2>
      <p className="mb-4 text-sm text-neutral-600">
        Only concepts and sections you have reached are shown, so there are no spoilers.
      </p>
      {map.isPending && <p role="status">Loading…</p>}
      {map.isError && <p role="alert">{map.error.message}</p>}
      {map.data && map.data.concepts.length === 0 && (
        <p role="status">
          No concepts yet. Set your reading progress, and make sure the book has finished
          processing.
        </p>
      )}
      {map.data && map.data.concepts.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <Heatmap data={map.data} selected={selected} onSelect={setSelected} />
          </div>
          {selected && <TrajectoryPanel documentId={documentId} conceptId={selected} />}
        </>
      )}
    </article>
  );
}
