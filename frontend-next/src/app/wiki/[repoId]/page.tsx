"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { WikiContent } from "@/components/wiki/WikiContent";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useRepo } from "@/hooks/useRepo";
import { useWikiPage } from "@/hooks/useWikiPage";
import { listRepos, ingestRepo, type Repo } from "@/lib/api";
import { useAppStore } from "@/store/appStore";

export default function WikiPage() {
  const params = useParams<{ repoId: string }>();
  const repoId = params.repoId ? parseInt(params.repoId) : null;
  const { user } = useAppStore();

  const [currentPath, setCurrentPath] = useState("overview");
  const [allRepos, setAllRepos] = useState<Repo[]>([]);
  const [reindexing, setReindexing] = useState(false);

  const { repo, loading: repoLoading, refetch: refetchRepo } = useRepo(repoId);
  const { page, loading: pageLoading, error: pageError } = useWikiPage(repoId, currentPath);

  useEffect(() => {
    if (!user) return;
    listRepos().then(setAllRepos).catch(() => {});
  }, [user]);

  // Reset to overview when switching repos
  useEffect(() => {
    setCurrentPath("overview");
  }, [repoId]);

  const handleNavigate = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleReindex = async () => {
    if (!repo) return;
    setReindexing(true);
    try {
      await ingestRepo(repo.url);
      refetchRepo();
    } catch {
    } finally {
      setReindexing(false);
    }
  };

  const handleSourceClick = useCallback((filePath: string) => {
    // Find the wiki structure page whose dir_path best matches this file path
    const structure = repo?.wiki_structure ?? [];
    const parts = filePath.split("/");
    for (let len = parts.length - 1; len > 0; len--) {
      const dir = parts.slice(0, len).join("/");
      const match = structure.find((p) => p.dir_path === dir);
      if (match) {
        setCurrentPath(match.dir_path);
        return;
      }
    }
    if (parts.length > 1) {
      setCurrentPath(parts.slice(0, -1).join("/"));
    }
  }, [repo]);

  // Find the current page title for the breadcrumb
  const currentPageTitle = repo?.wiki_structure?.find(
    (p) => p.dir_path === currentPath
  )?.title;

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <div className="text-center space-y-3">
          <p className="text-sm text-zinc-500">Please sign in to view wikis.</p>
          <a
            href="/api/auth/login"
            className="inline-flex items-center gap-2 px-4 py-2 rounded bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
          >
            Connect GitHub
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-white dark:bg-zinc-950 overflow-hidden">
      <TopBar
        repo={repo}
        currentPage={currentPath !== "overview" ? (currentPageTitle ?? currentPath) : undefined}
        onReindex={handleReindex}
        reindexing={reindexing}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          repo={repo}
          currentPath={currentPath}
          onNavigate={handleNavigate}
          allRepos={allRepos}
        />

        <main className="flex-1 overflow-y-auto">
          {repoLoading && !repo ? (
            <div className="p-8 space-y-3">
              <div className="h-7 w-48 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <WikiContent
              page={page}
              repo={repo}
              loading={pageLoading}
              error={pageError}
              onFileRef={handleSourceClick}
            />
          )}
        </main>

        <ChatPanel repoId={repoId} onSourceClick={handleSourceClick} />
      </div>
    </div>
  );
}
