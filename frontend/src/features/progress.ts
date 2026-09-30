import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";

export function useProgress(documentId: string) {
  return useQuery({
    queryKey: ["status", documentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/status", {
        params: { path: { document_id: documentId } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Could not load progress"));
      return data;
    },
  });
}

/** Saves the reading position. It gates every feature, so everything is refreshed afterwards. */
export function useSaveProgress(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (max_ordinal: number) => {
      const { error } = await api.PUT("/api/v1/documents/{document_id}/progress", {
        params: { path: { document_id: documentId } },
        body: { max_ordinal },
      });
      if (error) throw new Error(problemMessage(error, "Could not save progress"));
    },
    onSuccess: () => qc.invalidateQueries(),
  });
}
