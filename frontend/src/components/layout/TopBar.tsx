import { Link } from "react-router-dom";
import { Moon, Sun, RefreshCw, ChevronRight, Menu } from "lucide-react";
import { useAppStore } from "@/store/appStore";
import { cn } from "@/lib/utils";
import type { Repo } from "@/lib/api";

interface TopBarProps {
  repo?: Repo | null;
  currentPage?: string;
  onReindex?: () => void;
  reindexing?: boolean;
}

export function TopBar({ repo, currentPage, onReindex, reindexing }: TopBarProps) {
  const { darkMode, toggleDarkMode, toggleSidebar } = useAppStore();

  return (
    <header className="h-12 border-b border-zinc-200 dark:border-zinc-800 flex items-center px-4 gap-3 bg-white dark:bg-zinc-950 flex-shrink-0">
      {/* Mobile sidebar toggle */}
      <button
        onClick={toggleSidebar}
        className="md:hidden p-1 rounded text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
      >
        <Menu size={16} />
      </button>

      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm min-w-0 flex-1">
        <Link
          to="/"
          className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors flex-shrink-0"
        >
          CodeAtlas
        </Link>
        {repo && (
          <>
            <ChevronRight size={14} className="text-zinc-300 dark:text-zinc-700 flex-shrink-0" />
            <Link
              to={`/wiki/${repo.id}`}
              className="font-mono text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors truncate"
            >
              {repo.owner}/{repo.name}
            </Link>
          </>
        )}
        {currentPage && currentPage !== "overview" && (
          <>
            <ChevronRight size={14} className="text-zinc-300 dark:text-zinc-700 flex-shrink-0" />
            <span className="font-mono text-zinc-500 dark:text-zinc-400 truncate text-xs">
              {currentPage}
            </span>
          </>
        )}
      </nav>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {onReindex && (
          <button
            onClick={onReindex}
            disabled={reindexing}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium",
              "border border-zinc-200 dark:border-zinc-800",
              "text-zinc-600 dark:text-zinc-400",
              "hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <RefreshCw size={12} className={reindexing ? "animate-spin" : ""} />
            Re-index
          </button>
        )}

        <button
          onClick={toggleDarkMode}
          className="p-1.5 rounded text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          aria-label="Toggle dark mode"
        >
          {darkMode ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>
    </header>
  );
}
