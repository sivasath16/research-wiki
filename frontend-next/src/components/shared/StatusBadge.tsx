"use client";
import { cn } from "@/lib/utils";

type Status = "pending" | "indexing" | "ready" | "stale" | "failed";

interface StatusBadgeProps {
  status: Status;
  showLabel?: boolean;
  className?: string;
}

const config: Record<Status, { dot: string; label: string; bg: string; text: string }> = {
  pending: {
    dot: "bg-zinc-400",
    label: "Pending",
    bg: "bg-zinc-100 dark:bg-zinc-800",
    text: "text-zinc-600 dark:text-zinc-400",
  },
  indexing: {
    dot: "bg-amber-400 animate-pulse",
    label: "Indexing",
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
  },
  ready: {
    dot: "bg-[#1D9E75]",
    label: "Ready",
    bg: "bg-teal-50 dark:bg-teal-900/20",
    text: "text-teal-700 dark:text-teal-400",
  },
  stale: {
    dot: "bg-amber-500",
    label: "Stale",
    bg: "bg-amber-50 dark:bg-amber-900/20",
    text: "text-amber-700 dark:text-amber-400",
  },
  failed: {
    dot: "bg-red-500",
    label: "Failed",
    bg: "bg-red-50 dark:bg-red-900/20",
    text: "text-red-700 dark:text-red-400",
  },
};

export function StatusBadge({ status, showLabel = true, className }: StatusBadgeProps) {
  const c = config[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
        c.bg,
        c.text,
        className
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", c.dot)} />
      {showLabel && c.label}
    </span>
  );
}

export function StatusDot({ status }: { status: Status }) {
  const c = config[status];
  return <span className={cn("w-2 h-2 rounded-full flex-shrink-0", c.dot)} />;
}
