import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, problemMessage } from "../api/client";

export const authKeys = { me: ["auth", "me"] as const };

export function useMe() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/auth/me");
      if (response.status === 401) return null;
      if (!data) throw new Error("Failed to load session");
      return data;
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const { error } = await api.POST("/api/v1/auth/login", { body });
      if (error) throw new Error(problemMessage(error, "Login failed"));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: authKeys.me }),
  });
}

export function useSignup() {
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) => {
      const { error } = await api.POST("/api/v1/auth/signup", { body });
      if (error) throw new Error(problemMessage(error, "Sign-up failed"));
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/v1/auth/logout");
    },
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(authKeys.me, null);
    },
  });
}
