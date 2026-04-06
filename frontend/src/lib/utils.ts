import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceToNow } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "never";
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
  } catch {
    return "unknown";
  }
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}

export function getLanguageColor(lang: string | null): string {
  const colors: Record<string, string> = {
    TypeScript: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    JavaScript: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    Python: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    Go: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",
    Rust: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    Java: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    "C++": "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    C: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400",
  };
  return colors[lang || ""] || "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
}
