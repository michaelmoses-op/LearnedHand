import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";
import type { components } from "../api/schema";

export type Note = components["schemas"]["NoteOut"];

const keys = {
  notes: (d: string, q: string) => ["notes", d, q] as const,
};

export function useNotes(documentId: string, q: string) {
  return useQuery({
    queryKey: keys.notes(documentId, q),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/notes", {
        params: { path: { document_id: documentId }, query: q ? { q } : {} },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load notes"));
      return data.items;
    },
  });
}

export function useAddNote(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { kind: "note" | "highlight"; body: string; quote?: string }) => {
      const { data, error } = await api.POST("/api/v1/documents/{document_id}/notes", {
        params: { path: { document_id: documentId } },
        body: { kind: v.kind, body: v.body, quote: v.quote ?? null },
      });
      if (error || !data) throw new Error(problemMessage(error, "Could not save note"));
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", documentId] }),
  });
}

export function useDeleteNote(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (noteId: string) => {
      const { error } = await api.DELETE("/api/v1/documents/{document_id}/notes/{note_id}", {
        params: { path: { document_id: documentId, note_id: noteId } },
      });
      if (error) throw new Error(problemMessage(error, "Could not delete note"));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", documentId] }),
  });
}
