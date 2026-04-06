import { Link, useNavigate } from "react-router-dom";
import { BookOpen, Lock, ChevronRight, ChevronDown, Home } from "lucide-react";
import { cn } from "@/lib/utils";
import { StatusDot } from "../shared/StatusBadge";
import { useAppStore } from "@/store/appStore";
import type { Repo, WikiStructurePage } from "@/lib/api";
import { useState } from "react";

interface SidebarProps {
  repo: Repo | null;
  currentPath: string;
  onNavigate: (path: string) => void;
  allRepos?: Repo[];
}

interface TreeNode {
  page: WikiStructurePage;
  children: TreeNode[];
}

function buildTree(pages: WikiStructurePage[]): TreeNode[] {
  const map: Record<string, TreeNode> = {};
  for (const p of pages) {
    map[p.id] = { page: p, children: [] };
  }
  const roots: TreeNode[] = [];
  for (const p of pages) {
    if (p.parent_id && map[p.parent_id]) {
      map[p.parent_id].children.push(map[p.id]);
    } else {
      roots.push(map[p.id]);
    }
  }
  return roots;
}

function NavItem({
  node,
  depth,
  currentPath,
  onNavigate,
}: {
  node: TreeNode;
  depth: number;
  currentPath: string;
  onNavigate: (p: string) => void;
}) {
  const [open, setOpen] = useState(depth === 0);
  const { page, children } = node;
  const isActive = currentPath === page.dir_path;
  const hasChildren = children.length > 0;

  return (
    <div>
      <button
        onClick={() => {
          if (hasChildren) setOpen((o) => !o);
          onNavigate(page.dir_path);
        }}
        className={cn(
          "w-full flex items-center gap-1.5 py-1 pr-2 text-sm transition-colors rounded-r",
          "text-zinc-600 dark:text-zinc-400",
          "hover:text-zinc-900 dark:hover:text-zinc-100",
          isActive
            ? "bg-teal-50 dark:bg-teal-900/20 text-[#1D9E75] dark:text-[#1D9E75] border-l-2 border-[#1D9E75] font-medium"
            : "border-l-2 border-transparent"
        )}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {hasChildren ? (
          open
            ? <ChevronDown size={12} className="flex-shrink-0 opacity-60" />
            : <ChevronRight size={12} className="flex-shrink-0 opacity-60" />
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}
        <span className="truncate text-[13px]">{page.title}</span>
      </button>
      {open && children.map((child) => (
        <NavItem
          key={child.page.id}
          node={child}
          depth={depth + 1}
          currentPath={currentPath}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  );
}

export function Sidebar({ repo, currentPath, onNavigate, allRepos = [] }: SidebarProps) {
  const { sidebarOpen } = useAppStore();
  const navigate = useNavigate();

  if (!sidebarOpen) return null;

  const structure = repo?.wiki_structure ?? [];
  const tree = buildTree(structure);
  const otherRepos = allRepos.filter((r) => r.id !== repo?.id);
  const showFallback = structure.length === 0;

  return (
    <aside
      className={cn(
        "w-[220px] flex-shrink-0 border-r border-zinc-200 dark:border-zinc-800",
        "bg-white dark:bg-zinc-950 flex flex-col h-full overflow-hidden",
        "fixed md:relative z-10 md:z-auto"
      )}
    >
      {/* Logo */}
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center gap-2">
        <BookOpen size={16} className="text-[#1D9E75] flex-shrink-0" />
        <Link to="/" className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">
          ResearchWiki
        </Link>
      </div>

      {/* Repo pill */}
      {repo && (
        <div className="px-3 py-2 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-1.5 px-2 py-1.5 bg-zinc-100 dark:bg-zinc-900 rounded text-xs">
            <StatusDot status={repo.index_status} />
            {repo.is_private && <Lock size={11} className="text-zinc-400" />}
            <span className="font-mono text-zinc-700 dark:text-zinc-300 truncate">
              {repo.owner}/{repo.name}
            </span>
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2">
        {showFallback ? (
          <button
            onClick={() => onNavigate("overview")}
            className={cn(
              "w-full flex items-center gap-2 px-3 py-1 text-sm transition-colors",
              "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100",
              currentPath === "overview" &&
                "bg-teal-50 dark:bg-teal-900/20 text-[#1D9E75] border-l-2 border-[#1D9E75]"
            )}
          >
            <Home size={13} />
            Overview
          </button>
        ) : (
          <div className="px-1">
            {tree.map((node) => (
              <NavItem
                key={node.page.id}
                node={node}
                depth={0}
                currentPath={currentPath}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        )}

        {/* Other repos */}
        {otherRepos.length > 0 && (
          <div className="mt-4 pt-3 border-t border-zinc-100 dark:border-zinc-900">
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Other Repos
            </p>
            {otherRepos.slice(0, 5).map((r) => (
              <button
                key={r.id}
                onClick={() => navigate(`/wiki/${r.id}`)}
                className="w-full flex items-center gap-1.5 px-3 py-1 text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                <StatusDot status={r.index_status} />
                <span className="font-mono truncate">{r.owner}/{r.name}</span>
              </button>
            ))}
          </div>
        )}
      </nav>
    </aside>
  );
}
