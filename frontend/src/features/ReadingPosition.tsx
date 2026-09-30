import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId } from "react";
import { api, problemMessage } from "../api/client";

export type PositionSection = {
  id: string;
  ordinal: number;
  depth: number;
  title: string;
  last_chunk_ordinal: number | null;
};

const BEGINNING = "start";

/** "Where are you in the book?" Everything in the app is limited to this point. */
export function ReadingPosition({
  documentId,
  sections,
}: {
  documentId: string;
  sections: PositionSection[];
}) {
  const selectId = useId();
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["status", documentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/status", {
        params: { path: { document_id: documentId } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Could not load progress"));
      return data;
    },
  });
  const save = useMutation({
    mutationFn: async (max_ordinal: number) => {
      const { error } = await api.PUT("/api/v1/documents/{document_id}/progress", {
        params: { path: { document_id: documentId } },
        body: { max_ordinal },
      });
      if (error) throw new Error(problemMessage(error, "Could not save progress"));
    },
    // Progress gates every feature, so refresh everything that depends on it.
    onSuccess: () => qc.invalidateQueries(),
  });

  const stops = sections.filter((s) => s.last_chunk_ordinal !== null);
  const progress = status.data?.max_ordinal ?? null;
  const finished = stops.filter((s) => (s.last_chunk_ordinal ?? -1) <= (progress ?? -1));
  const current = finished.at(-1);
  const value = status.isPending ? "" : current ? current.id : BEGINNING;

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
