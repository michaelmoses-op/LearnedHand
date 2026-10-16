import { useQuery } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";

export function useSummaries(documentId: string) {
  return useQuery({
    queryKey: ["summaries", documentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/summaries", {
        params: { path: { document_id: documentId } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load summaries"));
      return data;
    },
  });
}
