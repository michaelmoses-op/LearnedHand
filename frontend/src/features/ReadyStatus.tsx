import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function ReadyStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["readyz"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/readyz");
      if (error || !data) throw new Error(`readyz ${response.status}`);
      return data;
    },
    retry: false,
  });

  if (isPending) return <p role="status">Checking API…</p>;
  if (isError) return <p role="alert">API not ready</p>;
  return <p role="status">API status: {data.status}</p>;
}
