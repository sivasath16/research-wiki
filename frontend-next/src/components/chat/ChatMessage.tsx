"use client";

import { cn } from "@/lib/utils";
import { CodeBlock } from "@/components/chat/CodeBlock";
import type { ChatMessage as ChatMessageType } from "@/hooks/useWebSocket";

interface ChatMessageProps {
  message: ChatMessageType;
  onSourceClick?: (filePath: string) => void;
}

function parseMarkdown(text: string) {
  const parts: Array<{ type: "text" | "code"; content: string; language?: string }> = [];
  const regex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    parts.push({ type: "code", language: match[1] || undefined, content: match[2] });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push({ type: "text", content: text.slice(lastIndex) });
  }

  return parts;
}

function InlineText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <p className="text-[13px] leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code
              key={i}
              className="font-mono text-[11px] px-1 py-0.5 rounded bg-zinc-800 text-zinc-200"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

export function ChatMessage({ message, onSourceClick }: ChatMessageProps) {
  const isUser = message.role === "user";
  const parts = parseMarkdown(message.content);

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2.5",
          isUser
            ? "bg-[#1D9E75] text-white rounded-br-sm"
            : "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 rounded-bl-sm"
        )}
      >
        {parts.map((part, i) => {
          if (part.type === "code") {
            return (
              <CodeBlock key={i} language={part.language}>
                {part.content}
              </CodeBlock>
            );
          }
          return <InlineText key={i} text={part.content} />;
        })}

        {message.streaming && (
          <span className="inline-block w-1.5 h-3.5 bg-current opacity-70 animate-pulse ml-0.5 align-middle" />
        )}

        {message.sources && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-700 space-y-1">
            <p className="text-[10px] text-zinc-400 uppercase tracking-wider font-medium">
              Sources
            </p>
            {message.sources.map((src, i) => (
              <button
                key={i}
                onClick={() => onSourceClick?.(src.file_path)}
                className="block font-mono text-[11px] text-[#1D9E75] hover:underline truncate max-w-full text-left"
              >
                {src.file_path}
                {src.name && ` — ${src.name}`}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
