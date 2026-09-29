import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api, problemMessage, readCsrfToken, refreshSession } from "../api/client";
import type { components } from "../api/schema";

export type DocumentOut = components["schemas"]["DocumentOut"];

export const docKeys = { list: ["documents"] as const };

export function useDocuments() {
  return useInfiniteQuery({
    queryKey: docKeys.list,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await api.GET("/api/v1/documents", {
        params: { query: pageParam ? { cursor: pageParam } : {} },
      });
      if (error || !data) throw new Error(problemMessage(error, "Failed to load library"));
      return data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

async function postFile(file: File): Promise<Response> {
  return fetch(`${window.location.origin}/api/v1/documents`, {
    method: "POST",
    credentials: "include",
    headers: {
      "X-Filename": encodeURIComponent(file.name),
      "X-CSRF-Token": readCsrfToken() ?? "",
      "Content-Type": "application/octet-stream",
    },
    body: file, // streamed by the browser; the server enforces the size cap
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      let res = await postFile(file);
      if (res.status === 401 && (await refreshSession())) res = await postFile(file);
      if (!res.ok)
        throw new Error(problemMessage(await res.json().catch(() => null), "Upload failed"));
      return (await res.json()) as DocumentOut;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.list }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/v1/documents/{document_id}", {
        params: { path: { document_id: id } },
      });
      if (error) throw new Error(problemMessage(error, "Delete failed"));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.list }),
  });
}
