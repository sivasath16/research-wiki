
import { useState, useEffect, useCallback, useRef } from "react";
import { getWikiPage, listWikiPages, type WikiPageFull, type WikiPageMeta } from "@/lib/api";

export function useWikiPage(repoId: number | null, path: string) {
  const [page, setPage] = useState<WikiPageFull | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    if (!repoId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getWikiPage(repoId, path || "overview");
      setPage(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load wiki page");
    } finally {
      setLoading(false);
    }
  }, [repoId, path]);

  useEffect(() => { load(); }, [load]);

  // Poll while page is generating — separate effect so cleanup is properly registered
  useEffect(() => {
    if (!page?.generating || !repoId) return;
    intervalRef.current = setInterval(async () => {
      try {
        const updated = await getWikiPage(repoId, path || "overview");
        setPage(updated);
      } catch {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    }, 2000);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [page?.generating, repoId, path]);

  return { page, loading, error, refetch: load };
}

export function useWikiPages(repoId: number | null) {
  const [pages, setPages] = useState<WikiPageMeta[]>([]);
  const [availableDirs, setAvailableDirs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!repoId) return;
    setLoading(true);
    listWikiPages(repoId)
      .then((data) => {
        setPages(data.pages);
        setAvailableDirs(data.available_dirs);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [repoId]);

  return { pages, availableDirs, loading };
}
