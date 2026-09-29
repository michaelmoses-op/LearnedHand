import { useQuery } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";
import type { components } from "../api/schema";

export type ConceptMap = components["schemas"]["ConceptMapOut"];
export type ConceptRow = components["schemas"]["ConceptRowOut"];
export type Trajectory = components["schemas"]["TrajectoryOut"];

export function useConceptMap(documentId: string, limit = 40) {
  return useQuery({
    queryKey: ["concepts", documentId, limit],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/documents/{document_id}/concepts", {
        params: { path: { document_id: documentId }, query: { limit } },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load concepts"));
      return data;
    },
  });
}

export function useTrajectory(documentId: string, conceptId: string | null) {
  return useQuery({
    queryKey: ["trajectory", documentId, conceptId],
    enabled: conceptId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/documents/{document_id}/concepts/{concept_id}/trajectory",
        { params: { path: { document_id: documentId, concept_id: conceptId ?? "" } } },
      );
      if (error || !data) throw new Error(problemMessage(error, "Failed to load trajectory"));
      return data;
    },
  });
}
