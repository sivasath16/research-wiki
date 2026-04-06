"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, Github, Moon, Sun, Plus, X, CheckCircle, Loader2 } from "lucide-react";
import { ingestRepo, listRepos, getLoginUrl, logout, jobStreamUrl, type Repo } from "@/lib/api";
import { RepoCard } from "@/components/shared/RepoCard";
import { RepoCardSkeleton } from "@/components/shared/SkeletonLoader";
import { useAppStore } from "@/store/appStore";
import { cn } from "@/lib/utils";

const PROGRESS_STEPS = [
  "Cloning repository",
  "Walking files",
  "Chunking files",
  "Embedding chunks",
  "Inserting chunks into database",
  "Building vector index",
  "Generating architecture diagram",
  "Finalizing",
];

interface IngestState {
  jobId: string | null;
  repoId: number | null;
  status: "idle" | "pending" | "running" | "completed" | "failed";
  step: string;
  pct: number;
  error: string | null;
}

export default function HomePage() {
  const { user, darkMode, toggleDarkMode } = useAppStore();
  const [url, setUrl] = useState("");
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [ingest, setIngest] = useState<IngestState>({
    jobId: null, repoId: null, status: "idle", step: "", pct: 0, error: null,
  });
  const router = useRouter();
  const esRef = useRef<EventSource | null>(null);

  const loadRepos = () => {
    if (!user) return;
    setLoadingRepos(true);
    listRepos()
      .then(setRepos)
      .catch(() => {})
      .finally(() => setLoadingRepos(false));
  };

  useEffect(() => {
    loadRepos();
  }, [user]);

  // SSE-based job progress
  useEffect(() => {
    if (!ingest.jobId || ingest.status === "completed" || ingest.status === "failed") return;

    esRef.current?.close();
    const es = new EventSource(jobStreamUrl(ingest.jobId), { withCredentials: true });
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const job = JSON.parse(event.data);
        setIngest((prev) => ({
          ...prev,
          status: job.status as IngestState["status"],
          step: job.progress_step || "",
          pct: job.progress_pct,
          error: job.error,
        }));

        if (job.status === "completed") {
          es.close();
          loadRepos();
          setTimeout(() => {
            router.push(`/wiki/${ingest.repoId}`);
          }, 800);
        } else if (job.status === "failed") {
          es.close();
          loadRepos();
        }
      } catch {}
    };

    es.onerror = () => es.close();

    return () => es.close();
  }, [ingest.jobId]);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || ingest.status === "running" || ingest.status === "pending") return;

    setIngest({ jobId: null, repoId: null, status: "pending", step: "Queuing...", pct: 0, error: null });

    try {
      const result = await ingestRepo(url.trim());
      if (result.status === "cached") {
        setIngest({ jobId: null, repoId: result.repo_id, status: "completed", step: "Already up to date", pct: 100, error: null });
        setTimeout(() => router.push(`/wiki/${result.repo_id}`), 500);
        return;
      }
      setIngest({
        jobId: result.job_id,
        repoId: result.repo_id,
        status: result.status as IngestState["status"],
        step: "Queued",
        pct: 0,
        error: null,
      });
    } catch (e: unknown) {
      setIngest({
        jobId: null, repoId: null, status: "failed",
        step: "", pct: 0,
        error: e instanceof Error ? e.message : "Ingestion failed",
      });
    }
  };

  const handleLogout = async () => {
    await logout();
    window.location.href = "/";
  };

  const isIngesting = ingest.status === "pending" || ingest.status === "running";

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 flex flex-col">
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        <div className="max-w-5xl mx-auto px-6 h-12 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-[#1D9E75]" />
            <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">
              ResearchWiki
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleDarkMode}
              className="p-1.5 rounded text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              {darkMode ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            {user ? (
              <div className="flex items-center gap-2">
                {user.avatar_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar_url} alt={user.login} className="w-6 h-6 rounded-full" />
                )}
                <span className="text-sm text-zinc-700 dark:text-zinc-300">{user.login}</span>
                <button
                  onClick={handleLogout}
                  className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <a
                href={getLoginUrl()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
              >
                <Github size={13} />
                Connect GitHub
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">
        <div className="max-w-2xl mx-auto px-6 pt-20 pb-12">
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-teal-50 dark:bg-teal-900/20 mb-4">
              <BookOpen size={22} className="text-[#1D9E75]" />
            </div>
            <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100 mb-2">
              Index any GitHub repo
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Generate a wiki and chat with the codebase using AI.
              Built for research groups.
            </p>
          </div>

          <form onSubmit={handleIngest} className="mb-8">
            <div className={cn(
              "flex gap-2 p-1.5 rounded-md border bg-white dark:bg-zinc-900",
              "border-zinc-200 dark:border-zinc-800",
              "focus-within:border-[#1D9E75] transition-colors"
            )}>
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                disabled={isIngesting || !user}
                className={cn(
                  "flex-1 px-3 py-2 text-sm bg-transparent outline-none",
                  "text-zinc-900 dark:text-zinc-100 placeholder-zinc-400",
                  "disabled:opacity-50"
                )}
              />
              <button
                type="submit"
                disabled={isIngesting || !url.trim() || !user}
                className={cn(
                  "px-4 py-2 rounded text-sm font-medium transition-colors",
                  "bg-[#1D9E75] text-white hover:bg-[#188f68]",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "flex items-center gap-2"
                )}
              >
                {isIngesting ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                {isIngesting ? "Indexing..." : "Index Repo"}
              </button>
            </div>

            {!user && (
              <p className="mt-2 text-xs text-zinc-400 text-center">
                <a href={getLoginUrl()} className="text-[#1D9E75] hover:underline">
                  Connect GitHub
                </a>{" "}
                to index repos
              </p>
            )}
          </form>

          {(isIngesting || ingest.status === "completed" || ingest.status === "failed") && (
            <div className={cn(
              "mb-8 border rounded-md p-4",
              ingest.status === "failed"
                ? "border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/10"
                : ingest.status === "completed"
                ? "border-teal-200 dark:border-teal-900/50 bg-teal-50 dark:bg-teal-900/10"
                : "border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900"
            )}>
              <div className="flex items-center gap-2 mb-3">
                {ingest.status === "completed" ? (
                  <CheckCircle size={14} className="text-[#1D9E75]" />
                ) : ingest.status === "failed" ? (
                  <X size={14} className="text-red-500" />
                ) : (
                  <Loader2 size={14} className="text-[#1D9E75] animate-spin" />
                )}
                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {ingest.status === "completed"
                    ? "Indexing complete!"
                    : ingest.status === "failed"
                    ? "Indexing failed"
                    : ingest.step || "Processing..."}
                </span>
                <span className="ml-auto text-xs text-zinc-400">{Math.round(ingest.pct)}%</span>
              </div>

              <div className="h-1 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500",
                    ingest.status === "failed" ? "bg-red-400" : "bg-[#1D9E75]"
                  )}
                  style={{ width: `${ingest.pct}%` }}
                />
              </div>

              {isIngesting && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {PROGRESS_STEPS.map((step, i) => (
                    <span
                      key={i}
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded-full",
                        ingest.step === step
                          ? "bg-[#1D9E75] text-white"
                          : ingest.pct > (i / PROGRESS_STEPS.length) * 100
                          ? "bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-400"
                          : "bg-zinc-100 dark:bg-zinc-800 text-zinc-400"
                      )}
                    >
                      {step}
                    </span>
                  ))}
                </div>
              )}

              {ingest.error && (
                <p className="mt-2 text-xs text-red-500">{ingest.error}</p>
              )}
            </div>
          )}
        </div>

        {user && (
          <div className="max-w-5xl mx-auto px-6 pb-16">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Indexed Repositories
              </h2>
              <span className="text-xs text-zinc-400">{repos.length} repos</span>
            </div>

            {loadingRepos ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {[1, 2, 3].map((i) => <RepoCardSkeleton key={i} />)}
              </div>
            ) : repos.length === 0 ? (
              <div className="border border-dashed border-zinc-200 dark:border-zinc-800 rounded-md p-12 text-center">
                <BookOpen size={24} className="text-zinc-300 dark:text-zinc-700 mx-auto mb-3" />
                <p className="text-sm text-zinc-400 mb-1">No repos indexed yet</p>
                <p className="text-xs text-zinc-400">Paste a GitHub URL above to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {repos.map((repo) => (
                  <RepoCard key={repo.id} repo={repo} onDelete={loadRepos} />
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
