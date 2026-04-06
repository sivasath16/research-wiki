
import { useState, useEffect, useCallback } from "react";
import { getRepo, type Repo } from "@/lib/api";

export function useRepo(repoId: number | null) {
  const [repo, setRepo] = useState<Repo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getRepo(repoId);
      setRepo(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load repo");
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => { load(); }, [load]);

  return { repo, loading, error, refetch: load };
}
