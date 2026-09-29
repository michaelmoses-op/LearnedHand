import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";
import type { components } from "../api/schema";

export type Note = components["schemas"]["NoteOut"];
export type Flashcard = components["schemas"]["FlashcardOut"];
export type QuizQuestion = components["schemas"]["QuizQuestionOut"];
export type Rating = components["schemas"]["ReviewIn"]["rating"];

const keys = {
  notes: (d: string, q: string) => ["notes", d, q] as const,
  cards: (d: string) => ["flashcards", d] as const,
  quiz: (d: string) => ["quiz", d] as const,
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

export function useFlashcards(documentId: string, dueOnly: boolean) {
  return useQuery({
    queryKey: [...keys.cards(documentId), dueOnly],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/flashcards", {
        params: { path: { document_id: documentId }, query: { due: dueOnly } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load flashcards"));
      return data.items;
    },
  });
}

export function useReview(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { cardId: string; rating: Rating }) => {
      const { data, error } = await api.POST(
        "/api/v1/documents/{document_id}/flashcards/{card_id}/review",
        {
          params: { path: { document_id: documentId, card_id: v.cardId } },
          body: { rating: v.rating },
        },
      );
      if (error || !data) throw new Error(problemMessage(error, "Could not save review"));
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.cards(documentId) }),
  });
}

export function useQuiz(documentId: string) {
  return useQuery({
    queryKey: keys.quiz(documentId),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/quiz", {
        params: { path: { document_id: documentId } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load quiz"));
      return data.items;
    },
  });
}

export function useAnswer(documentId: string) {
  return useMutation({
    mutationFn: async (v: { questionId: string; choice: number }) => {
      const { data, error } = await api.POST(
        "/api/v1/documents/{document_id}/quiz/{question_id}/answer",
        {
          params: { path: { document_id: documentId, question_id: v.questionId } },
          body: { choice: v.choice },
        },
      );
      if (error || !data) throw new Error(problemMessage(error, "Could not check answer"));
      return data;
    },
  });
}

export function useGenerate(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (kind: "flashcards" | "quiz") => {
      const { data, error } = await api.POST("/api/v1/documents/{document_id}/study/generate", {
        params: { path: { document_id: documentId } },
        body: { kind, count: 5 },
      });
      if (error || !data) throw new Error(problemMessage(error, "Could not generate"));
      return data;
    },
    onSuccess: (_d, kind) =>
      qc.invalidateQueries({ queryKey: [kind === "quiz" ? "quiz" : "flashcards", documentId] }),
  });
}
