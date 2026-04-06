import { Link } from "react-router-dom";
import { Lock, Trash2 } from "lucide-react";
import { type Repo, deleteRepo } from "@/lib/api";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { cn, getLanguageColor, timeAgo } from "@/lib/utils";
import { useState } from "react";

interface RepoCardProps {
  repo: Repo;
  onDelete?: () => void;
}

export function RepoCard({ repo, onDelete }: RepoCardProps) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Delete ${repo.owner}/${repo.name}? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await deleteRepo(repo.id);
      onDelete?.();
    } catch {
      setDeleting(false);
    }
  };

  return (
    <Link
      to={`/wiki/${repo.id}`}
      className={cn(
        "group block border border-zinc-200 dark:border-zinc-800 rounded-md p-4",
        "hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-900/50",
        "transition-all duration-150"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {repo.is_private && (
            <Lock size={12} className="text-zinc-400 flex-shrink-0" />
          )}
          <span className="font-mono text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate">
            {repo.owner}/{repo.name}
          </span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <StatusBadge status={repo.index_status} />
          <button
            onClick={handleDelete}
            disabled={deleting}
            className={cn(
              "p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity",
              "text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
            )}
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {repo.description && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3 line-clamp-2">
          {repo.description}
        </p>
      )}

      <div className="flex items-center gap-3 text-xs text-zinc-400">
        {repo.language && (
          <span
            className={cn(
              "px-1.5 py-0.5 rounded-full text-xs font-medium",
              getLanguageColor(repo.language)
            )}
          >
            {repo.language}
          </span>
        )}
        {repo.indexed_at && (
          <span>Indexed {timeAgo(repo.indexed_at)}</span>
        )}
        {repo.chunk_count > 0 && (
          <span>{repo.chunk_count.toLocaleString()} chunks</span>
        )}
      </div>

      {repo.index_status === "failed" && repo.error_message && (
        <p className="mt-2 text-xs text-red-500 border border-red-200 dark:border-red-900/50 rounded px-2 py-1 bg-red-50 dark:bg-red-900/20">
          {repo.error_message.slice(0, 120)}
        </p>
      )}
    </Link>
  );
}
