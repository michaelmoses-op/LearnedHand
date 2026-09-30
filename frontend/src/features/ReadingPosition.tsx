import { useId } from "react";
import { useProgress, useSaveProgress } from "./progress";

export type PositionSection = {
  id: string;
  ordinal: number;
  depth: number;
  title: string;
  last_chunk_ordinal: number | null;
};

const BEGINNING = "start";
const PARTIAL = "partial";

/** "Where are you in the book?" Everything in the app is limited to this point. */
export function ReadingPosition({
  documentId,
  sections,
}: {
  documentId: string;
  sections: PositionSection[];
}) {
  const selectId = useId();
  const status = useProgress(documentId);
  const save = useSaveProgress(documentId);

  const stops = sections.filter((s) => s.last_chunk_ordinal !== null);
  const progress = status.data?.max_ordinal ?? null;
  const finished = stops.filter((s) => (s.last_chunk_ordinal ?? -1) <= (progress ?? -1));
  const current = finished.at(-1);
  // Progress can sit mid-section (marked at a paragraph); then it matches no "End of …" stop.
  const midSection = progress !== null && progress > 0 && current?.last_chunk_ordinal !== progress;
  const partial = midSection
    ? stops.find((s) => (s.last_chunk_ordinal ?? -1) > (progress ?? -1))
    : undefined;
  const value = status.isPending ? "" : partial ? PARTIAL : current ? current.id : BEGINNING;

  function onChange(next: string) {
    if (next === BEGINNING) return save.mutate(0);
    const target = stops.find((s) => s.id === next);
    if (target?.last_chunk_ordinal != null) save.mutate(target.last_chunk_ordinal);
  }

  if (stops.length === 0) return null;
  return (
    <div className="notice flex flex-wrap items-center gap-3">
      <label htmlFor={selectId} className="font-semibold">
        I have read up to
      </label>
      <select
        id={selectId}
        className="field !w-auto min-w-0 max-w-full flex-1 sm:max-w-md"
        value={value}
        disabled={save.isPending || status.isPending}
        onChange={(e) => onChange(e.target.value)}
      >
        {status.isPending && (
          <option value="" disabled>
            Loading…
          </option>
        )}
        {partial && (
          <option value={PARTIAL} disabled>
            {`Partway through “${partial.title}”`}
          </option>
        )}
        <option value={BEGINNING}>The beginning (first passage only)</option>
        {stops.map((s) => (
          <option key={s.id} value={s.id}>
            {`${"— ".repeat(s.depth)}End of “${s.title}”`}
          </option>
        ))}
      </select>
      <span className="muted text-sm">Answers and study material never go past this point.</span>
      {save.isError && (
        <p role="alert" className="alert w-full">
          {save.error.message}
        </p>
      )}
    </div>
  );
}
