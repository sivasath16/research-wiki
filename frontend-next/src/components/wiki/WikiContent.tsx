"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { MermaidDiagram } from "@/components/wiki/MermaidDiagram";
import { WikiPageSkeleton } from "@/components/shared/SkeletonLoader";
import { cn, copyToClipboard, getLanguageColor, timeAgo } from "@/lib/utils";
import type { WikiPageFull, Repo } from "@/lib/api";

interface WikiContentProps {
  page: WikiPageFull | null;
  repo: Repo | null;
  loading: boolean;
  error: string | null;
  onFileRef?: (path: string) => void;
}

function InlineCode({ children }: { children: React.ReactNode }) {
  const text = String(children);
  const [copied, setCopied] = useState(false);

  const isFilePath = text.includes("/") || text.includes(".py") || text.includes(".ts");

  const handleClick = () => {
    if (!isFilePath) return;
    copyToClipboard(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <code
      onClick={handleClick}
      className={cn(
        "font-mono text-[0.85em] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800",
        "text-zinc-800 dark:text-zinc-200",
        isFilePath && "text-[#1D9E75] cursor-pointer hover:bg-teal-50 dark:hover:bg-teal-900/20 transition-colors"
      )}
      title={isFilePath ? (copied ? "Copied!" : "Click to copy") : undefined}
    >
      {copied ? "✓" : children}
    </code>
  );
}

function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    copyToClipboard(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (language === "mermaid") {
    return <MermaidDiagram diagram={children} className="my-4" />;
  }

  return (
    <div className="relative my-4 group">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-t-md">
        {language && (
          <span className="font-mono text-[11px] text-zinc-400">{language}</span>
        )}
        <button
          onClick={handleCopy}
          className={cn(
            "ml-auto flex items-center gap-1 text-[11px] px-2 py-0.5 rounded",
            "text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
          )}
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 bg-zinc-950 dark:bg-zinc-950 border border-t-0 border-zinc-200 dark:border-zinc-800 rounded-b-md">
        <code className="font-mono text-xs text-zinc-200 leading-relaxed">{children}</code>
      </pre>
    </div>
  );
}

export function WikiContent({ page, repo, loading, error, onFileRef: _onFileRef }: WikiContentProps) {
  if (loading) return <WikiPageSkeleton />;

  if (error) {
    return (
      <div className="p-8">
        <div className="border border-red-200 dark:border-red-900/50 rounded-md p-4 bg-red-50 dark:bg-red-900/10">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  if (!page) return null;

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-xl font-medium text-zinc-900 dark:text-zinc-100 mb-3">
          {page.title}
        </h1>
        {repo && (
          <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
            {repo.language && (
              <span className={cn("px-2 py-0.5 rounded-full font-medium", getLanguageColor(repo.language))}>
                {repo.language}
              </span>
            )}
            {repo.indexed_at && (
              <span>Last indexed {timeAgo(repo.indexed_at)}</span>
            )}
            {repo.file_count > 0 && (
              <span>{repo.file_count.toLocaleString()} files</span>
            )}
            {repo.chunk_count > 0 && (
              <span>{repo.chunk_count.toLocaleString()} chunks</span>
            )}
          </div>
        )}
      </div>

      {repo?.index_status === "stale" && (
        <div className="mb-6 px-4 py-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded text-sm text-amber-700 dark:text-amber-400 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
          This repo has new commits. Re-index to get the latest content.
        </div>
      )}

      {page.mermaid_diagram && (
        <div className="mb-6">
          <MermaidDiagram diagram={page.mermaid_diagram} />
        </div>
      )}

      {page.content_md && (
        <div className="prose prose-zinc dark:prose-invert max-w-none prose-sm">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children }) {
                const match = /language-(\w+)/.exec(className || "");
                const lang = match?.[1] || "";

                if (lang || String(children).includes("\n")) {
                  return (
                    <CodeBlock language={lang}>{String(children).replace(/\n$/, "")}</CodeBlock>
                  );
                }
                return <InlineCode>{children}</InlineCode>;
              },
              a({ href, children }) {
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#1D9E75] hover:underline"
                  >
                    {children}
                  </a>
                );
              },
              h1: ({ children }) => (
                <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mt-8 mb-3 pb-2 border-b border-zinc-200 dark:border-zinc-800">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100 mt-6 mb-2">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 mt-4 mb-1">
                  {children}
                </h3>
              ),
              p: ({ children }) => (
                <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed mb-3">
                  {children}
                </p>
              ),
              ul: ({ children }) => (
                <ul className="text-sm text-zinc-700 dark:text-zinc-300 list-disc list-inside space-y-1 mb-3">
                  {children}
                </ul>
              ),
              li: ({ children }) => <li className="leading-relaxed">{children}</li>,
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-zinc-300 dark:border-zinc-700 pl-4 text-zinc-500 dark:text-zinc-400 italic my-3">
                  {children}
                </blockquote>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-4">
                  <table className="w-full text-sm border-collapse border border-zinc-200 dark:border-zinc-800">
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th className="px-3 py-2 text-left font-medium bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="px-3 py-2 border border-zinc-200 dark:border-zinc-800 text-xs">
                  {children}
                </td>
              ),
            }}
          >
            {page.content_md}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}
